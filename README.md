# Digital Dark Spot

**Find what your sources aren't telling you.**

An AI-assisted information gap detection platform, built for the Shinchan Online Hackathon 2026 (Devengers) by Joyshree (individual participation).

## Problem

Important decisions about education, loans and public services rely on web pages that are scattered, outdated or conflicting. Search tools find pages and summarizers shorten them, but neither tells people what is missing or what they should check before acting.

## What it does

Add 2-6 sources (web page URLs, PDF links or pasted text) and a research question. The app shows:

- **Coverage matrix:** which source covers which fact, with the exact quote behind each cell
- **Dark spots:** facts a person needs that no source mentions
- **Conflicts:** contradicting claims shown side by side with verified quotes
- **Freshness warnings:** rule-based checks from page metadata, server headers and years mentioned in the text, plus AI-detected signals
- **Unanswered questions** the sources leave open
- **Verify-next checklist:** prioritized, with where to verify each item
- **Evidence panel:** click any cell to see the quote highlighted inside its surrounding text

## What makes it different

- **Not a summarizer or chatbot.** The output is about what is missing and uncertain, not a shorter version of the pages.
- **"No quote, no claim."** The AI must attach an exact quote to every finding. Python code checks that the quote really exists in the source text; claims whose quote cannot be matched are labelled *Unverified*.
- **AI proposes, code verifies.** Quote checking and freshness rules are plain code, not AI.
- **Clear labels** separate verified source evidence, AI suggestions and rule-based checks.
- **Built for messy real sources:** PDF support, a paste-text fallback, and clear messages when a page cannot be read.

## How it works

1. The user enters a research question and adds sources.
2. The backend fetches each page or PDF and extracts its text and any dates. Pages that cannot be read can be pasted manually.
3. One Gemini request identifies the facts the question needs and checks which sources cover them, quoting the evidence.
4. Python code verifies every quote against the original source text and runs the freshness checks.
5. The dashboard shows the results with source references.

## Limitations

- **A verified quote is not a verified fact.** "Verified" means the quote exists in that source. The source itself can be wrong, and a quote can lose meaning when read out of context.
- AI findings are potential gaps and signals, not guaranteed facts. The AI can miss a gap or conflict, or wrongly treat two statements as being about the same thing. Always confirm important details with the official source.
- Some websites need JavaScript or block automated readers; use "Paste text" for those. Scanned PDFs (images) are not read.
- Each source is limited to 30,000 characters.
- The free Gemini tier has rate limits and can be busy. The app retries and falls back to other models, but analyses can still fail temporarily.
- Freshness checks rely on dates found in the page, which can be missing or wrong.

## Tech stack

- Python and Flask (backend)
- HTML, CSS and JavaScript (frontend, no framework)
- Requests, BeautifulSoup and pypdf (reading web pages and PDFs)
- Google Gemini API via `google-genai` (gap, conflict and freshness-signal detection)
- python-dotenv (API key handling)

## Project structure

```
app.py          Flask server and API route
fetcher.py      Downloads pages and PDFs, extracts text and dates
analyzer.py     Gemini call, quote verification, matrix building
freshness.py    Rule-based outdated / undated source checks
templates/
  index.html    The whole interface
requirements.txt
```

## How to run

1. Clone the repository and open the folder:
   `git clone https://github.com/joyshreeanandha8-eng/digital-dark-spot.git`
2. Create a virtual environment: `python -m venv venv`
3. Activate it (Windows PowerShell): `venv\Scripts\Activate.ps1`
4. Install dependencies: `pip install -r requirements.txt`
5. Get a free API key from Google AI Studio, then create a file named `.env` in the project folder:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash
GEMINI_FALLBACKS=gemini-3.8-flash,gemini-3.1-flash-lite
```

`GEMINI_FALLBACKS` is optional. These backup models are used if the main model is busy. Model names change over time; check which ones your key can use in AI Studio.

6. Start the app: `python app.py`
7. Open the local address shown in the terminal (usually http://127.0.0.1:5000).

## Demo

Question: *"What should I verify before applying for the PM Vidyalaxmi education loan scheme?"*

Suggested sources (add them as URLs):

- https://www.angelone.in/news/personal-finance/pm-vidya-laxmi-education-loan-know-more-details-about-scheme
- https://patrika.com/en/education-news/5-points-about-pm-vidya-lakshmi-yojana-10-lakh-education-loan-yojana-approved-by-pm-modi-cabinet-19133919
- https://businesstoday.in/personal-finance/story/pm-vidyalaxmi-scheme-centre-to-offer-collateral-free-guarantor-free-education-loans-to-students-check-eligibility-application-process-452924-2024-11-07

The "Load sample sources" button fills in two clearly labelled **fictional** sources for a quick test.

## Security notes

- The API key lives in `.env`, which is excluded from the repository by `.gitignore`.
- The server refuses URLs that point to localhost or private networks.
- All text from sources and from the AI is escaped before it is displayed.

## Future scope

Automatic discovery of official sources, OCR for scanned PDFs, Tamil and other Indian languages, saved and exportable research reports, confidence scoring for findings, and a stricter check that two conflicting statements apply to the same group or component.
