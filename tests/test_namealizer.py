import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from chat import ChatEngine, ChatError
from namealizer import SOURCES, Candidate, WebSearch, WordHistory, describe_existing, generate, queries, research_prompt, run, screen, select
from settings import Settings, configure, load_settings


def candidate(name="Memora"):
    return Candidate(name=name, origin="Invented from memory", meaning="Remember your story", kind="blend")


class NamingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(directory.cleanup)
        self.history_path = Path(directory.name) / "word-history.json"
        override = patch("namealizer.HISTORY", self.history_path)
        override.start()
        self.addCleanup(override.stop)

    def test_ten_names_with_vowel_dropped_kind_are_kept(self):
        names = ["Mnemos", "Logos", "Scribeon", "Vellum", "Lexis", "Mythos",
                 "Codexi", "Verbit", "Graphos", "Narrat"]
        items = [candidate(name).model_dump() for name in names]
        items[-1] = {
            "name": "Narrat",
            "origin": "Latin (narrare) with dropped vowel",
            "meaning": "A shortened, punchy form of 'narrate' or 'narrative'.",
            "kind": "vowel-dropped",
        }
        for prefix in ("", "Output: ", "Output: ```json\n"):
            raw = prefix + json.dumps(items) + ("\n```" if "```" in prefix else "")
            with self.subTest(prefix=prefix):
                engine = Mock(get_response=Mock(return_value=raw))
                result = generate(engine, "Writing app", "memory", 0, [], set(), "")
                self.assertEqual([n.name for n in result], names)
                self.assertEqual(result[-1].kind, "vowel-dropped")
                engine.get_response.assert_called_once()

    def test_kind_is_freeform_feedback_and_optional(self):
        item = candidate().model_dump()
        for label in ("Portmanteau", "poetic shortening", "something-unrecognised", ""):
            item["kind"] = label
            self.assertEqual(Candidate.model_validate(item).kind, label)
        del item["kind"]
        self.assertEqual(Candidate.model_validate(item).kind, "")

    def test_generated_names_are_validated_and_deduplicated(self):
        engine = Mock()
        engine.get_response.return_value = "```json\n" + json.dumps([
            candidate().model_dump(), candidate("memora").model_dump(),
            candidate("Novara").model_dump()]) + "\n```"
        names = generate(engine, "Writing app", "memory", 0, [], {"novara"}, "")
        self.assertEqual([n.name for n in names], ["Memora"])

    def test_invalid_model_output_is_recoverable(self):
        for text in ('not JSON', '{}', '[]', '[{"name": "oops"}]'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                generate(Mock(get_response=Mock(return_value=text)), "app", "write", 0, [], set(), "")

    def test_search_operator_injection_is_rejected(self):
        with self.assertRaises(ValueError):
            candidate('foo" OR bar')

    def test_selection_is_atomic_and_deduplicated(self):
        self.assertEqual(select("1, 3 1", 3), [0, 2])
        self.assertEqual(select("", 3), [])
        for text in ("0", "4", "1,no", "-1"):
            with self.assertRaises(ValueError):
                select(text, 3)

    def test_queries_are_fixed_and_include_all_categories(self):
        self.assertEqual(queries("Memora")["GitHub"], '"Memora" site:github.com')
        self.assertEqual(len(queries("Memora")), 5)

    def test_search_failure_is_unknown_not_available(self):
        with patch("builtins.print") as output:
            report = screen(candidate(), Mock(side_effect=RuntimeError("offline")))
        self.assertIsNone(report["screening_score"])
        self.assertTrue(all(c["status"] == "failed" for c in report["checks"].values()))
        self.assertTrue(all(c["error"] == "RuntimeError: offline" for c in report["checks"].values()))
        self.assertTrue(any("offline" in str(call) for call in output.call_args_list))

    def test_search_requests_are_paced_across_queries(self):
        client = Mock(text=Mock(return_value=[{"title": "name", "href": "https://example.com"}]))
        search = WebSearch(client)
        with patch("namealizer.time.monotonic", return_value=100), \
                patch("namealizer.time.sleep") as sleep, patch("builtins.print"):
            search("first")
            search("second")
        sleep.assert_called_once_with(2.0)
        self.assertEqual(client.text.call_count, 2)

    def test_search_fallback_waits_and_keeps_same_fixed_query(self):
        from ddgs.exceptions import TimeoutException
        client = Mock(text=Mock(side_effect=[TimeoutException("operation timed out"),
                                            [{"title": "name", "href": "https://example.com"}]]))
        search = WebSearch(client)
        with patch("namealizer.time.monotonic", return_value=100), \
                patch("namealizer.time.sleep") as sleep, patch("builtins.print") as output:
            results = search('"Memora" software app project')
        sleep.assert_called_once_with(4.0)
        self.assertEqual([c.kwargs["backend"] for c in client.text.call_args_list], ["duckduckgo", "brave"])
        self.assertTrue(all(c.args[0] == '"Memora" software app project' for c in client.text.call_args_list))
        self.assertEqual(results[0]["search_backend"], "brave")
        self.assertTrue(any("TimeoutException: operation timed out" in str(c) for c in output.call_args_list))

    def test_failed_search_is_bounded_and_preserves_both_backend_errors(self):
        from ddgs.exceptions import DDGSException
        client = Mock(text=Mock(side_effect=DDGSException("No results found.")))
        with patch("namealizer.time.sleep"), patch("builtins.print"), self.assertRaises(RuntimeError) as caught:
            WebSearch(client)("name")
        self.assertEqual(client.text.call_count, 2)
        self.assertIn("duckduckgo: DDGSException: No results found.", str(caught.exception))
        self.assertIn("brave: DDGSException: No results found.", str(caught.exception))

    def test_empty_provider_reply_is_not_scored_as_success(self):
        client = Mock(text=Mock(return_value=[]))
        with patch("namealizer.time.sleep"), patch("builtins.print"), self.assertRaises(RuntimeError):
            WebSearch(client)("name")

    def test_scoring_uses_exact_mentions_not_number_of_hits(self):
        search = Mock(return_value=[{"title": "Memorable software", "href": "https://example.com", "body": ""}])
        self.assertEqual(screen(candidate(), search)["screening_score"], 100)
        search.return_value = [{"title": "Memora", "href": "https://example.com", "body": ""}]
        self.assertEqual(screen(candidate(), search)["screening_score"], 0)
        self.assertEqual(search.call_count, 10)

    def test_partial_failure_never_yields_score(self):
        search = Mock(side_effect=[[], [], RuntimeError(), [], []])
        with patch("builtins.print"):
            self.assertIsNone(screen(candidate(), search)["screening_score"])

    def test_favourites_persist_across_rounds(self):
        answers = ["Writing app", "novel,memory", "", "m", "", "1", "m", "more Latin", "1", "s", "y", ""]
        with patch("builtins.input", side_effect=answers), patch("builtins.print"), \
                patch("namealizer.generate", side_effect=[[candidate()], [candidate("Novara")]]) as gen, \
                patch("namealizer.screen", side_effect=lambda c: {"candidate": c.model_dump()}) as check, \
                patch("namealizer.print_report"):
            run(Mock())
        self.assertEqual([c.args[0].name for c in check.call_args_list], ["Memora", "Novara"])
        self.assertEqual(gen.call_args.args[-1], "more Latin")
        self.assertEqual(gen.call_args.args[4][0].name, "Memora")

    def test_declining_search_never_calls_search(self):
        answers = ["app", "memory", "", "m", "", "1", "s", "n", "q"]
        with patch("builtins.input", side_effect=answers), patch("builtins.print"), \
                patch("namealizer.generate", return_value=[candidate()]), \
                patch("namealizer.screen") as check:
            run(Mock())
        check.assert_not_called()

    def test_topic_is_shown_before_guidance_and_guidance_can_be_reused_or_cleared(self):
        answers = iter(["Writing app", "memory", "", "m", "", "", "m", "short names",
                        "", "m", "y", "", "m", "n", "", "", "q"])
        guidance_rounds = set()
        with patch("builtins.print") as output:
            def answer(prompt):
                if prompt.startswith(("Guidance for this topic", "Reuse previous guidance")):
                    topic_index = gen.call_count
                    output.assert_any_call(f"\nRound {topic_index + 1} topic: {SOURCES[topic_index]}")
                    previous = "" if topic_index <= 1 else "short names"
                    output.assert_any_call(f"Previous guidance: {previous or '(none)'}")
                    guidance_rounds.add(topic_index)
                return next(answers)

            with patch("builtins.input", side_effect=answer), \
                    patch("namealizer.generate", return_value=[candidate()]) as gen:
                run(Mock())
        self.assertEqual([call.args[-1] for call in gen.call_args_list],
                         ["", "short names", "short names", ""])
        self.assertEqual(len(guidance_rounds), 4)

    def test_variations_use_full_favourites_and_can_be_kept_before_screening(self):
        original = candidate()
        variant = candidate("Memorix")
        answers = ["Writing app", "memory", "", "m", "", "1", "v", "short blends", "1", "f", "s", "y", ""]
        with patch("builtins.input", side_effect=answers), patch("builtins.print") as output, \
                patch("namealizer.generate", side_effect=[[original], [variant]]) as gen, \
                patch("namealizer.screen", side_effect=lambda c: {"candidate": c.model_dump()}) as check, \
                patch("namealizer.print_report"):
            run(Mock())
        self.assertFalse(gen.call_args_list[0].kwargs["variations"])
        self.assertTrue(gen.call_args_list[1].kwargs["variations"])
        self.assertEqual(gen.call_args_list[1].args[4][0], original)
        self.assertEqual([c.args[0] for c in check.call_args_list], [original, variant])
        output.assert_any_call(f"1. {original.name} [{original.kind}] — {original.meaning}\n"
                               f"    Origin (unverified): {original.origin}")

    def test_variation_prompt_combines_favourites_and_explains_parent_words(self):
        engine = Mock(get_response=Mock(return_value=json.dumps([candidate("Memorix").model_dump()])))
        generate(engine, "Writing app", "memory", 0, [candidate()], {"memora"}, "short", variations=True)
        prompt = engine.get_response.call_args.args[0]
        self.assertIn("Combine favourites into portmanteaus", prompt)
        self.assertIn("Explain which favourites", prompt)
        self.assertIn(candidate().meaning, prompt)

    def test_variations_require_a_favourite(self):
        with patch("builtins.input", side_effect=["app", "memory", "", "m", "", "", "v", "q"]), \
                patch("builtins.print") as output, \
                patch("namealizer.generate", return_value=[candidate()]) as gen, \
                patch("namealizer.screen") as check:
            run(Mock())
        gen.assert_called_once()
        check.assert_not_called()
        output.assert_any_call("Keep at least one favourite first.")

    def test_own_ideas_retain_notes_for_variations_and_screening(self):
        answers = ["app", "memory", "", "m", "", "", "a", "Novelix", "Novel plus helix", "v", "",
                   "", "a", "Scriptix", "Script plus helix", "s", "y", ""]
        snapshots = []

        def generated(*args, **kwargs):
            snapshots.append([n.model_dump() for n in args[4]])
            return [candidate()]

        with patch("builtins.input", side_effect=answers), patch("builtins.print"), \
                patch("namealizer.generate", side_effect=generated), \
                patch("namealizer.screen", side_effect=lambda c: {"candidate": c.model_dump()}) as check, \
                patch("namealizer.print_report"):
            run(Mock())
        self.assertEqual(snapshots[1][0]["name"], "Novelix")
        self.assertEqual(snapshots[1][0]["meaning"], "Novel plus helix")
        self.assertEqual([c.args[0].name for c in check.call_args_list], ["Novelix", "Scriptix"])

    def test_own_ideas_handle_duplicates_cancellation_and_invalid_names(self):
        answers = ["app", "memory", "", "m", "", "1", "a", "memora", "a", "", "a", "bad name",
                   "note", "a", "Novelix", "", "s", "y", ""]
        with patch("builtins.input", side_effect=answers), patch("builtins.print") as output, \
                patch("namealizer.generate", return_value=[candidate()]), \
                patch("namealizer.screen", side_effect=lambda c: {"candidate": c.model_dump()}) as check, \
                patch("namealizer.print_report"):
            run(Mock())
        self.assertEqual([c.args[0].name for c in check.call_args_list], ["Memora", "Novelix"])
        output.assert_any_call("That name is already a favourite.")

    def test_existing_words_get_descriptions_in_one_call_preserving_spelling(self):
        engine = Mock(get_response=Mock(return_value=json.dumps([
            candidate("memora").model_dump(), candidate("Novara").model_dump()])))
        with patch("builtins.print"):
            result = describe_existing(engine, "Memora, Novara memora", "Writing app", "memory")
        self.assertEqual([n.name for n in result], ["Memora", "Novara"])
        self.assertEqual(result[0].meaning, candidate().meaning)
        engine.get_response.assert_called_once()

    def test_existing_words_survive_failed_or_partial_model_descriptions(self):
        for reply in ("invalid JSON", json.dumps([candidate().model_dump()])):
            with self.subTest(reply=reply), patch("builtins.print"):
                engine = Mock(get_response=Mock(return_value=reply))
                result = describe_existing(engine, "Memora Novara", "app", "memory")
                self.assertEqual([n.name for n in result], ["Memora", "Novara"])
                self.assertEqual(result[1].meaning, "Carried over from a previous run")
        engine = Mock(get_response=Mock(side_effect=ChatError("offline")))
        with patch("builtins.print"):
            self.assertEqual(describe_existing(engine, "Memora", "app", "memory")[0].name, "Memora")

    def test_empty_existing_words_need_no_model_call(self):
        engine = Mock()
        self.assertEqual(describe_existing(engine, "", "app", "memory"), [])
        engine.get_response.assert_not_called()

    def test_word_history_survives_restart_and_keeps_original_descriptions(self):
        history = WordHistory(self.history_path)
        history.remember([candidate()])
        history = WordHistory(self.history_path)
        revised = candidate("MEMORA").model_copy(update={"meaning": "Different explanation"})
        history.remember([revised])
        engine = Mock()
        with patch("builtins.print"):
            words = describe_existing(engine, "MEMORA", "other project", "new keywords", history)
        self.assertEqual(words[0].name, "MEMORA")
        self.assertEqual(words[0].meaning, candidate().meaning)
        self.assertEqual(WordHistory(self.history_path).words["memora"].meaning, candidate().meaning)
        engine.get_response.assert_not_called()

    def test_only_unknown_words_are_described_and_then_cached(self):
        history = WordHistory(self.history_path)
        history.remember([candidate()])
        engine = Mock(get_response=Mock(return_value=json.dumps([candidate("Novara").model_dump()])))
        with patch("builtins.print"):
            words = describe_existing(engine, "Memora Novara", "app", "memory", history)
        prompt = engine.get_response.call_args.args[0]
        self.assertIn("Novara", prompt)
        self.assertNotIn("Memora", prompt)
        self.assertEqual([w.name for w in words], ["Memora", "Novara"])
        self.assertIn("novara", WordHistory(self.history_path).words)

    def test_failed_descriptions_are_not_cached_as_known_words(self):
        history = WordHistory(self.history_path)
        history.remember([candidate()])
        engine = Mock(get_response=Mock(side_effect=ChatError("offline")))
        with patch("builtins.print"):
            words = describe_existing(engine, "Memora Novara", "app", "memory", history)
        self.assertEqual(words[0].meaning, candidate().meaning)
        self.assertEqual(words[1].meaning, "Carried over from a previous run")
        self.assertNotIn("novara", WordHistory(self.history_path).words)

    def test_all_generated_words_are_saved_even_without_favourites(self):
        with patch("builtins.input", side_effect=["app", "memory", "", "m", "", "", "q"]), \
                patch("builtins.print"), \
                patch("namealizer.generate", return_value=[candidate(), candidate("Novara")]):
            run(Mock())
        self.assertEqual(set(WordHistory(self.history_path).words), {"memora", "novara"})

    def test_invalid_history_is_preserved(self):
        self.history_path.write_text("broken JSON", encoding="utf-8")
        with self.assertRaises(ValueError):
            WordHistory(self.history_path)
        self.assertEqual(self.history_path.read_text(encoding="utf-8"), "broken JSON")

    def test_initial_menu_can_skip_first_topic_before_any_generation(self):
        engine = Mock()
        with patch("builtins.input", side_effect=["app", "memory", "", "n", "m", "", "", "q"]), \
                patch("builtins.print") as output, \
                patch("namealizer.generate", return_value=[candidate()]) as gen:
            run(engine)
        gen.assert_called_once()
        self.assertEqual(gen.call_args.args[3], 1)
        output.assert_any_call(f"Next topic for more names: {SOURCES[0]}")
        engine.get_response.assert_not_called()

    def test_initial_menu_quit_makes_no_model_call(self):
        engine = Mock()
        with patch("builtins.input", side_effect=["app", "memory", "", "q"]), \
                patch("builtins.print"), patch("namealizer.generate") as gen:
            run(engine)
        gen.assert_not_called()
        engine.get_response.assert_not_called()

    def test_research_prompt_contains_context_favourites_and_evidence_requirements(self):
        word = candidate().model_copy(update={"meaning": "My own explanation"})
        prompt = research_prompt("Offline writing workspace", "novel, memory", [word])
        for expected in ("Offline writing workspace", "novel, memory", word.name,
                         word.origin, "My own explanation", "GitHub", "official registers",
                         "similar-sounding", "Link directly", "cannot browse", "investigate manually"):
            self.assertIn(expected, prompt)

    def test_research_prompt_can_be_printed_without_network_and_returns_to_menu(self):
        WordHistory(self.history_path).remember([candidate()])
        engine = Mock()
        with patch("builtins.input", side_effect=["app", "memory", "Memora", "p", "f", "q"]), \
                patch("builtins.print") as output, patch("namealizer.screen") as screen_call, \
                patch("namealizer.generate") as generate_call:
            run(engine)
        output.assert_any_call("--- BEGIN RESEARCH PROMPT ---")
        output.assert_any_call("--- END RESEARCH PROMPT ---\n")
        self.assertTrue(any("Project and shortlist:" in str(call) for call in output.call_args_list))
        engine.get_response.assert_not_called()
        screen_call.assert_not_called()
        generate_call.assert_not_called()

    def test_research_prompt_requires_favourites(self):
        with patch("builtins.input", side_effect=["app", "memory", "", "p", "q"]), \
                patch("builtins.print") as output:
            run(Mock())
        output.assert_any_call("Keep at least one favourite first.")
        self.assertFalse(any("BEGIN RESEARCH PROMPT" in str(call) for call in output.call_args_list))

    def test_user_descriptions_are_saved_on_quit_interrupt_and_end_of_input(self):
        for index, ending in enumerate(("q", KeyboardInterrupt(), EOFError())):
            with self.subTest(ending=ending):
                path = self.history_path.with_name(f"exit-{index}.json")
                history = WordHistory(path)
                answers = ["app", "memory", "", "a", "Novelix", "My own explanation", ending]
                with patch("namealizer.WordHistory", return_value=history), \
                        patch.object(history, "save", wraps=history.save) as saved, \
                        patch("builtins.input", side_effect=answers), patch("builtins.print"):
                    if isinstance(ending, BaseException):
                        with self.assertRaises(type(ending)):
                            run(Mock())
                    else:
                        run(Mock())
                self.assertEqual(saved.call_count, 2)  # Immediate write plus the exit flush.
                self.assertEqual(WordHistory(path).words["novelix"].meaning, "My own explanation")

    def test_interrupt_during_favourite_selection_keeps_all_generated_descriptions(self):
        with patch("builtins.input", side_effect=["app", "memory", "", "m", "", KeyboardInterrupt()]), \
                patch("builtins.print"), \
                patch("namealizer.generate", return_value=[candidate(), candidate("Novara")]):
            with self.assertRaises(KeyboardInterrupt):
                run(Mock())
        self.assertEqual(set(WordHistory(self.history_path).words), {"memora", "novara"})

    def test_user_description_takes_priority_over_cached_model_description(self):
        WordHistory(self.history_path).remember([candidate()])
        answers = ["app", "memory", "", "a", "Memora", "My explanation", "q"]
        with patch("builtins.input", side_effect=answers), patch("builtins.print"):
            run(Mock())
        self.assertEqual(WordHistory(self.history_path).words["memora"].meaning, "My explanation")

    def test_menu_can_skip_multiple_topics_and_wrap_without_model_calls(self):
        answers = ["app", "memory", "", "m", "", "1", *(["n"] * 5), "m", "", "", "q"]
        with patch("builtins.input", side_effect=answers), patch("builtins.print") as output, \
                patch("namealizer.generate", return_value=[candidate()]) as gen:
            run(Mock())
        self.assertEqual(gen.call_count, 2)
        self.assertEqual(gen.call_args.args[3], 6)
        self.assertEqual(gen.call_args.args[4][0].name, "Memora")
        for source in SOURCES:
            output.assert_any_call(f"Next topic for more names: {source}")

    def test_guidance_skip_advances_topic_without_sending_skip_to_model(self):
        answers = ["app", "memory", "", "m", "", "", "m", "/skip", "short names", "", "q"]
        with patch("builtins.input", side_effect=answers), patch("builtins.print") as output, \
                patch("namealizer.generate", return_value=[candidate()]) as gen:
            run(Mock())
        self.assertEqual(gen.call_count, 2)
        self.assertEqual(gen.call_args.args[3], 2)
        self.assertEqual(gen.call_args.args[-1], "short names")
        output.assert_any_call(f"\nRound 3 topic: {SOURCES[2]}")

    def test_skip_at_reuse_prompt_preserves_guidance_for_next_topic(self):
        answers = ["app", "memory", "", "m", "", "", "m", "short names", "", "m",
                   "/skip", "y", "", "q"]
        with patch("builtins.input", side_effect=answers), patch("builtins.print"), \
                patch("namealizer.generate", return_value=[candidate()]) as gen:
            run(Mock())
        self.assertEqual(gen.call_count, 3)
        self.assertEqual(gen.call_args.args[3], 3)
        self.assertEqual(gen.call_args.args[-1], "short names")

    def test_startup_words_are_kept_and_passed_to_generation(self):
        engine = Mock(get_response=Mock(return_value=json.dumps([candidate().model_dump()])))
        with patch("builtins.input", side_effect=["app", "memory", "Memora", "m", "", "", "f", "q"]), \
                patch("builtins.print") as output, \
                patch("namealizer.generate", return_value=[candidate("Novara")]) as gen:
            run(engine)
        self.assertEqual(gen.call_args.args[4][0].meaning, candidate().meaning)
        self.assertIn("memora", gen.call_args.args[5])
        output.assert_any_call(f"1. Memora [blend] — {candidate().meaning}\n"
                               f"    Origin (unverified): {candidate().origin}")


class ConfigAndChatTests(unittest.TestCase):
    def test_remote_requires_explicit_consent_and_https(self):
        for options in ({"base_url": "https://example.com/v1"},
                        {"base_url": "http://example.com/v1", "allow_remote": True},
                        {"base_url": "https://user:secret@example.com/v1", "allow_remote": True}):
            with self.assertRaises(ValueError):
                Settings(**options)
        Settings(base_url="https://example.com/v1", allow_remote=True)
        Settings()

    def test_configure_and_load_both_profiles_without_saving_secret(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            path = Path(directory) / "config.json"
            answers = ["", "local-test", "https://example.com/v1", "remote-test", "y"]
            with patch("builtins.input", side_effect=answers), patch("builtins.print"), \
                    patch.dict("os.environ", {"NAMEALIZER_API_KEY": "private-key"}):
                configure(path)
                self.assertEqual(load_settings("local", path).model, "local-test")
                remote = load_settings("remote", path)
                self.assertTrue(remote.allow_remote)
                self.assertEqual(remote.api_key.get_secret_value(), "private-key")
            self.assertNotIn("private-key", path.read_text())
            self.assertNotIn("api_key", path.read_text())

    def test_reused_chat_client_sends_payload_and_keeps_no_history(self):
        def respond(request):
            payload = json.loads(request.content)
            self.assertEqual(payload["model"], "local-model")
            self.assertEqual(payload["messages"][-1]["content"], "names please")
            self.assertEqual(request.headers["Authorization"], "Bearer secret")
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "[]"}}]})
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            engine = ChatEngine(Settings(api_key="secret"), client)
            self.assertEqual(engine.get_response("names please"), "[]")
            self.assertEqual(engine.history, [])

    def test_chat_errors_do_not_leak_server_body_or_credentials(self):
        for status in (401, 302):
            with httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(status, text="private-key"))) as client:
                with self.assertRaises(ChatError) as caught:
                    ChatEngine(Settings(), client).get_response("names")
                self.assertNotIn("private-key", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
