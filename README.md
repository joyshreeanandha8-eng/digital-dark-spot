# Digital Dark Spot

AI-assisted information gap detection platform.

## Problem

Important decisions about education, loans and public services rely on web pages that are scattered, outdated or conflicting. Search tools find pages and summarizers shorten them, but neither tells people what is missing or what they should check before acting.

## What it does

Add 2-6 sources (URLs or pasted text) and a research question. The app shows:

- **Coverage matrix:** which source covers which fact, with the exact quote
- **Dark spots:** facts that no source mentions
- **Conflicts:** contradicting claims shown side by side with verified quotes
- **Freshness warnings:** outdated or undated information
- **Unanswered questions** the sources leave open
- **Verify-next checklist:** prioritized, with where to verify each item

## How it works

1. The user enters a research question and adds sources.
2. The backend fetches each page and extracts its text. Pages that cannot be read can be pasted manually.
3. The Gemini AI model identifies the facts needed for the question and checks which sources cover them.
4. Python code verifies every quoted claim against the original source text. Quotes that cannot be matched are labelled Unverified.
5. The dashboard shows the results with source references.

AI findings are potential gaps and signals, not guaranteed facts. Always confirm important details with the official source.

## Tech stack

- Python and Flask (backend)
- HTML, CSS and JavaScript (frontend)
- Requests and BeautifulSoup (fetching and reading web pages)
- Google Gemini API via google-genai (gap, conflict and freshness detection)
- python-dotenv (API key handling)
- Python code that verifies every quote against the source text

## How to run

1. Clone the repository and open the folder.
2. Create a virtual environment: `python -m venv venv`
3. Activate it: `venv\Scripts\activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Create a file named `.env` in the project folder and add your Gemini API key:
   `GEMINI_API_KEY=your_key_here`
6. Start the app: `python app.py`
7. Open the local address shown in the terminal (usually http://127.0.0.1:5000).

## Demo

Try this question with three or more sources:
"What should I verify before applying for the PM Vidyalaxmi education loan scheme?"

Suggested sources:
- https://www.angelone.in/news/personal-finance/pm-vidya-laxmi-education-loan-know-more-details-about-scheme
- https://patrika.com/en/education-news/5-points-about-pm-vidya-lakshmi-yojana-10-lakh-education-loan-yojana-approved-by-pm-modi-cabinet-19133919
- https://businesstoday.in/personal-finance/story/pm-vidyalaxmi-scheme-centre-to-offer-collateral-free-guarantor-free-education-loans-to-students-check-eligibility-application-process-452924-2024-11-07

## Future scope

Automatic discovery of official sources, PDF support, multiple languages, saved research reports, detection of the application cycle or year in each source, and confidence scoring for findings.
