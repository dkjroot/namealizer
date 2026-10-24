# namealizer
Simple LLM enhanced project name finder

## Free to use. Please help keep it that way.

I develop this project to be freely available to everyone, supported, if at all,
by voluntary contributions. I do not want other people to profit from my work
by selling copies, putting it behind a paywall, or building a paid application
or hosted service around it. I ask you to respect that intention: please keep
this work freely available, credit its origins, and direct people to
[my official GitHub repository](https://github.com/dkjroot/namealizer) for the software.

If you want to help fund my development, please contribute **directly to me**
through [Buy Me a Coffee](https://buymeacoffee.com/dkjroot). Paying a distributor
or hosting provider does not fund my work unless I explicitly say otherwise.
There is no obligation to contribute.

**This is a personal request, not an additional license restriction.** The
[GNU General Public License v3.0](LICENSE) permits commercial use and
redistribution, including forks, subject to its terms. Those legal permissions
remain unchanged by this request.

**[Support my work on Buy Me a Coffee](https://buymeacoffee.com/dkjroot)**

## What it does

Finding a name is easy. Finding one that somebody else hasn't already used
for much the same thing is a bit more of a pain. That's what this is for.

Tell it what your project does and give it a few keywords. It'll suggest ten
short names, with a little explanation of each. Keep the ones you like, then
ask for another ten if you want. Your favourites stay on the list.
At the start, you can also paste existing words from a previous run, separated
by commas or spaces. It'll ask the model for descriptions and add them straight
to your favourites. Known words reuse their saved descriptions; only unknown
words need a model call. If that call fails, your words are still kept.
The menu appears before the first naming round too: choose `m` to generate
names, `n` to skip the previewed topic, or work with your existing favourites.

All generated names and descriptions are remembered in `word-history.json`
beside the script, whether or not you favourite them. It's a local dictionary
across all runs and topics, ignored by Git. Existing descriptions are kept,
so a reused explanation may refer to an earlier project and is still unverified.
Your own ideas are remembered too if you give them a description. Remove the
file if you want to start with an empty history.
Descriptions are saved as you go and the history is saved again when you leave,
including with Ctrl+C or end-of-input. Your written descriptions take priority
over older saved descriptions of the same name.

The rounds work through different languages and mythologies, alongside
made-up names, portmanteaus and contractions. You can give it a steer between
rounds, such as "more Latin blends" or "less mythological". Before each new
round, it'll show you the next topic and offer to reuse your previous guidance.
If you don't reuse it, type new guidance or just press Enter for none. Origins and
meanings come from the model, so treat them as suggestions to check.
The favourites menu previews the next topic. Type `n` there to move past
it without calling the model, then choose `m` when you reach one you like.
You can also type `/skip` when asked for guidance or whether to reuse it.

Once you've got a few favourites, choose `p` for a research prompt you can
paste into your own chat and ask it to search the web. That is the recommended
way to check GitHub projects, software, companies, trademarks and word origins.
The old automatic search option is still there if you want to try it.

## IMPORTANT NOTE

Even if this tool suggests that a word is usable as a new trademark or project
name, you should check it out yourself thoroughly before using it. In the end
it's your responsibility to pick a unique name for your project!

## Getting going

You'll need Python 3.11 or later and a chat server offering the usual
OpenAI-compatible `/v1/chat/completions` endpoint. You can configure a local
server and a hosted one, and choose which to use. No speech packages or
model downloads are included.

On Windows, in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe namealizer.py --configure
.\.venv\Scripts\python.exe namealizer.py
```

On Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python namealizer.py --configure
.venv/bin/python namealizer.py
```

Run these from the project folder. The configuration wizard asks for a base
URL and model name for each profile. For a local server, try its address
ending in `/v1`, such as `http://127.0.0.1:5001/v1`. Leave the remote URL
blank if you don't need it. Start your local model server separately.

For the remote profile, add `--profile remote` when you run the script.
The wizard asks permission to send your project description, keywords and
favourites to that endpoint. Remote endpoints require HTTPS. Local mode
accepts loopback addresses only and doesn't fall back to a hosted model.

If your chosen endpoint needs a key, set `NAMEALIZER_API_KEY` in your shell
before running it. Replace `your-api-key-here` with your actual key.

On Windows, in PowerShell:

```powershell
$env:NAMEALIZER_API_KEY = 'your-api-key-here'
.\.venv\Scripts\python.exe namealizer.py --profile remote
```

On Linux, in Bash:

```bash
export NAMEALIZER_API_KEY='your-api-key-here'
.venv/bin/python namealizer.py --profile remote
```

These set the key for the current shell session. Run the script from that
same terminal. Don't put the key into a command you plan to share.
Configuration is saved in the ignored `local-config.json`; keys aren't saved.
The local configuration format follows Iris's chat settings, but there are
no speech or audio settings to work through.

## Choosing and checking names

Enter favourite numbers separated by commas or spaces. Choose `m` for more
names, `v` for variations on your favourites, `a` to add your own idea,
`f` to see your favourites
with their original descriptions and origins, `r` to remove favourites,
`p` for a research prompt, `s` to try automatic screening, or `q` to stop.
Variations use the names you've kept to suggest ten portmanteaus, contractions
and other invented words, explaining where each came from. Keep any you like
alongside the originals, and repeat as often as you want before searching.
You can add your own names at any of these selection stages, with an optional
description or note about their roots. They'll stay with your other favourites
and can be used for variations or checked online in exactly the same way.
The shortlist lasts for the current run. After screening, you can save the
results to a new JSON file; an existing file won't be overwritten. Use a
name beginning `namealizer-report` to keep it out of Git automatically.

## Checking your shortlist: the practical way

We ran into repeated timeouts and apparent blocking from search engines when
trying to search automatically. Slowing it down and trying another engine
didn't reliably fix it. The errors don't prove a blacklist, but scraping
search pages has turned out to be too unreliable to depend on here.

For this little project, the practical compromise is `p`: it prints a complete
prompt containing your project description, keywords and favourites, including
their saved explanations. Copy everything between the BEGIN and END markers
into your own chat and ask it to use web search. I use ChatGPT for this.
The prompt asks for evidence links, similar-name conflicts, checks of word
origins, a risk comparison and the limits of any trademark searches. It also
asks the chat to say if it can't browse, rather than make up results.

Printing the prompt makes no model or search calls. Nothing is sent anywhere
until you paste it into your chosen service, so review the included project
details before sharing it. You can print it again after changing your shortlist.

## Automatic screening: unreliable

The `s` option is retained, but may fail completely if providers block requests.
It asks permission separately, even with a local model. It sends
only your favourite names in fixed queries to DuckDuckGo, with Brave as a
fallback, using
[DDGS](https://github.com/deedy5/ddgs). Your project description and keywords
aren't part of those searches. No search API key is needed.

The screening score starts at 100 and loses 25 for each of GitHub, software,
companies and trademarks where the returned snippets mention the exact name.
Only three results are requested per query. Higher means fewer surfaced
mentions; it isn't a probability that a name is available. An incomplete
conflict search gets an unknown score. Provenance results are shown separately
for you to check against the model's explanation.

**Before settling on a favourite, investigate it manually.** These searches
aren't exhaustive and don't establish that a name is free. Check similar
spellings, related products, relevant official trademark registers and the
claimed word origins. For names from living cultural traditions, check that
the proposed use is appropriate too.

If the model returns unusable output, you can retry. If searches fail or get
rate-limited, the report includes the fixed queries and manual search links.
Requests are spaced at least two seconds apart, with four seconds after a
failure. Each query tries DuckDuckGo, then Brave if needed; there's no endless
retry loop. Backend names and exception messages are printed to the console
and failures are included in saved reports, so you can copy the errors when
reporting a problem. "No results found" can also mean a provider blocked the
request; it isn't treated as proof that a name is free.
If the model can't be reached, check its server, URL and model name first.

## Tests and reused code

The tests run offline with fake model and search responses. On Windows:

```powershell
.\.venv\Scripts\python.exe test.py
```

On Linux:

```bash
.venv/bin/python test.py
```

You get one short summary if they pass, and details if anything fails.

The chat client in `chat.py` is reused from
[Iris](https://github.com/dkjroot/iris-llm), with its settings import adjusted.
The configuration validation is adapted from Iris too. Both projects use
GPL v3; this keeps the useful chat bits without bringing in the audio stack.
The Python dependencies are HTTPX (BSD-3-Clause), Pydantic (MIT) and DDGS
(MIT), plus their dependencies, which retain their own licences.
