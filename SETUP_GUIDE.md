# UK Restaurant Pricing Intelligence Tool
## Plain-English Setup Guide

---

## What this tool does

This is a private web page that runs on your own computer. You open it in your
browser like any website, but it only works when your laptop is on — nobody else
can see it. It lets you:

- Upload your monthly pricing Excel file and have it automatically analysed
- See which brands have priced, how broadly and how heavily
- Compare brands, time periods and individual items
- Ask questions in plain English and get data-driven answers
- Build up a historical database over time as you add new monthly files

---

## Before you start — what you need

You need three things. None of them cost money except a small amount for the
question-answering feature (pennies per question).

**1. Python**
Python is free software that makes the tool run. Think of it like the engine
under the bonnet — you never see it, but the tool needs it.

**2. The tool files**
The folder called `pricing_app` that came with this guide. Keep everything
in it together — do not move individual files out of the folder.

**3. A Claude API key** (only needed for the "Ask a Question" feature)
This is what lets you type questions and get answers. It costs roughly £0.01–£0.02
per question. You get it from Anthropic's website — instructions below.

---

## Step 1 — Install Python (skip if you already have it)

1. Go to **python.org/downloads** in your browser
2. Click the big yellow "Download Python" button
3. Open the downloaded file and run the installer
4. **Important:** on the first screen of the installer, tick the box that says
   **"Add Python to PATH"** before clicking Install
5. Click Install Now and wait for it to finish
6. Close the installer

To check it worked: open the Terminal app on Mac (search "Terminal" in Spotlight)
or Command Prompt on Windows (search "cmd" in the Start menu). Type `python --version`
and press Enter. You should see something like `Python 3.12.0`. If you do, Python
is installed correctly.

---

## Step 2 — Put the tool files somewhere sensible

Take the `pricing_app` folder and put it somewhere you'll remember — your Desktop
or your Documents folder works well. The folder should contain:

```
pricing_app/
    app.py
    requirements.txt
    data/              ← this is where your data will be stored automatically
    SETUP_GUIDE.md     ← this file
```

---

## Step 3 — Install the tool's dependencies

Dependencies are small pieces of free software the tool needs to run. You only
do this once.

**On Mac:**
1. Open Terminal (search "Terminal" in Spotlight)
2. Type the following and press Enter — replace the path with wherever you put
   the pricing_app folder:
   ```
   cd ~/Desktop/pricing_app
   ```
   (If you put it in Documents, use `cd ~/Documents/pricing_app` instead)
3. Then type this and press Enter:
   ```
   pip install -r requirements.txt
   ```
4. Wait. You will see a lot of text scrolling past — this is normal. It takes
   1–3 minutes. When it stops and you see a `$` prompt again, it is done.

**On Windows:**
1. Open Command Prompt (search "cmd" in the Start menu)
2. Type the following and press Enter:
   ```
   cd C:\Users\YourName\Desktop\pricing_app
   ```
   Replace `YourName` with your actual Windows username and adjust the path
   if you put the folder somewhere other than the Desktop.
3. Then type this and press Enter:
   ```
   pip install -r requirements.txt
   ```
4. Wait for it to finish (1–3 minutes).

If you see an error saying `pip` is not recognised, try `pip3` instead of `pip`.

---

## Step 4 — Get your Claude API key (for the question-answering feature)

You can skip this step if you only want the dashboard and don't need to ask
free-text questions. You can always come back to it later.

1. Go to **console.anthropic.com** in your browser
2. Create a free account (just an email address and password)
3. Once logged in, click **"API Keys"** in the left menu
4. Click **"Create Key"**, give it a name like "Pricing Tool", and click Create
5. Copy the key that appears — it starts with `sk-ant-`
6. **Save it somewhere safe** (like a password manager or a note). You will not
   be able to see it again after you close that screen.

The key costs nothing to create. You are only charged when you use it — roughly
£0.01–£0.02 per question you ask the tool.

---

## Step 5 — Start the tool

Every time you want to use the tool, do this:

**On Mac:**
1. Open Terminal
2. Type `cd ~/Desktop/pricing_app` (or wherever you put it) and press Enter
3. Type `streamlit run app.py` and press Enter
4. Your browser will automatically open to the tool. The address will be
   something like `http://localhost:8501`
5. Leave the Terminal window open while you use the tool — closing it will
   stop the tool

**On Windows:**
1. Open Command Prompt
2. Type `cd C:\Users\YourName\Desktop\pricing_app` and press Enter
3. Type `streamlit run app.py` and press Enter
4. Your browser will automatically open to the tool
5. Leave the Command Prompt window open while you use the tool

---

## Step 6 — Upload your first data file

1. In the tool, look at the left sidebar (the dark panel on the left)
2. You will see a box that says "Drop a pricing Excel file here"
3. Click it and select your pricing Excel file — the same format as the
   `Pricing_Report_-_March_2026.xlsx` file
4. Wait a few seconds while it processes
5. You will see a green confirmation message when it is done

The data is now stored in a small database file inside the `data` folder.
You only need to upload each month's file once — the tool remembers everything.

---

## Step 7 — Use the tool

The tool has four sections, shown as tabs at the top:

**Market Overview**
The headline view. Shows which brands have priced, the market median move,
a classification breakdown, and a chart of when brands are pricing.
Use the "Years to analyse" selector to focus on a specific period.

**Brand Detail**
Drill into a single brand. See how every item has changed between two years,
and get a full list of the specific items that moved in the most recent period.

**Full Table**
The complete brand-by-brand comparison table with all classifications, breadth
percentages, and absolute moves. Can be downloaded as a CSV.

**Ask a Question**
Type any question in plain English. Enter your Claude API key in the sidebar
first. Examples of questions that work well:
- "Which brands have the most restructuring activity this year?"
- "How does Nando's pricing compare to KFC?"
- "Which brands repriced broadly but lightly in 2026?"
- "What would I expect to see from April movers based on historical patterns?"

---

## Adding new data each month

When you receive a new monthly pricing file:

1. Start the tool as normal (Step 5)
2. Upload the new file using the sidebar
3. The tool will automatically check what is already in the database and only
   add the new records — you will not get duplicates

Over time the database builds up a complete picture across months and years,
making the comparisons and trend analysis more powerful.

---

## If something goes wrong

**The tool won't start / "streamlit not recognised"**
The dependencies did not install correctly. Go back to Step 3 and try again.
If you see a specific error message, copy it and ask Claude for help.

**"No data loaded" message**
You need to upload a file first. See Step 6.

**The question-answering feature isn't working**
Check that you entered your API key in the sidebar (the left panel). It should
start with `sk-ant-`. If the key is correct but it still fails, the most likely
cause is a network issue.

**The file won't upload**
Check that your Excel file has a sheet called "Raw Data" and that it is in the
same column format as the original pricing report. The tool will not work with
a differently structured file.

---

## Stopping the tool

When you are done, go back to the Terminal or Command Prompt window and press
`Ctrl + C`. This stops the tool. Your data is saved automatically — nothing
is lost.

---

## A note on privacy and cost

All your data is stored in the `data` folder on your own computer. Nothing is
sent to any external server except when you use the "Ask a Question" feature,
which sends a summary of the data (not the raw file) to the Claude API to
generate an answer. The raw pricing files themselves never leave your machine.

API costs for the question-answering feature are typically £0.01–£0.02 per
question. You can monitor your usage at console.anthropic.com.

---

*Tool built to the methodology established in the UK Restaurant Pricing
Intelligence analysis, April 2026. Classification rules, breadth denominator
and true-change detection logic are locked into the code and apply consistently
on every upload.*
