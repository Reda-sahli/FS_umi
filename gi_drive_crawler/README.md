# 🚀 Setup Guide — Google Drive API Crawler

## Files in this folder
```
drive_crawler/
├── crawl_drive.py          ← Main crawler script
├── requirements.txt        ← Python dependencies
├── README.md               ← This file
├── credentials.json        ← (YOU PROVIDE) OAuth2 Desktop App key
│   OR
├── service_account.json    ← (YOU PROVIDE) Service Account key
└── gi_database_final.json  ← (GENERATED) Output file
```

---

## Step 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Step 2 — Choose your authentication method

### ✅ Option A — Service Account (Recommended for production)
Best when the folders are publicly shared or shared with the service account.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable **Google Drive API**:
   - APIs & Services → Library → Search "Google Drive API" → Enable
4. Create a Service Account:
   - APIs & Services → Credentials → Create Credentials → Service Account
   - Name it anything (e.g. `gi-portal-crawler`)
   - Skip optional steps → Done
5. Create a key for it:
   - Click the service account → Keys tab → Add Key → JSON
   - Save the downloaded file as **`service_account.json`** in this folder
6. **Share the Drive folders with the service account email**:
   - Find the service account email (looks like `name@project-id.iam.gserviceaccount.com`)
   - Open each semester folder in Drive → Share → paste the email → Viewer access

```
S3: https://drive.google.com/drive/folders/1Uydpe13HG_HekDJ436jj66D62wkoVlUo
S4: https://drive.google.com/drive/folders/1up_Ht85GujXL2CH03dM1kUAWVAAw8CKi
S5: https://drive.google.com/drive/folders/1ji08TCdWwlndE5KvB6VqircU26ZLwNim
S6: https://drive.google.com/drive/folders/1lHZJ7BlH6rSpCI6tcpmrqGf-p7WjlTJN
```

> **Note**: If the folders are already publicly visible ("Anyone with the link"),
> you still need to share them with the service account email for API access.

---

### 🔁 Option B — OAuth2 Desktop App (Recommended for personal use)
Best when you are the owner of the folders and running locally.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Drive API**
3. Configure OAuth Consent Screen:
   - APIs & Services → OAuth consent screen
   - User Type: **External** → Fill in App name → Save
   - Scopes: add `.../auth/drive.readonly`
   - Test users: add your own Google account email
4. Create OAuth2 credentials:
   - APIs & Services → Credentials → Create Credentials → OAuth Client ID
   - Application type: **Desktop app**
   - Download the JSON → save as **`credentials.json`** in this folder
5. Run the script — a browser window will open asking you to sign in with Google
6. After authorization, a `token.json` is saved locally for future runs

---

## Step 3 — Run the crawler

```bash
python crawl_drive.py
```

### What happens:
1. 🔑 Authenticates with Google Drive API
2. 📂 Recursively traverses all 4 semester folders (S3 → S4 → S5 → S6)
3. 📄 Extracts every file's: name, ID, MIME type, folder path
4. 🏷️ Classifies each file into: `COUR | TD | TP | EXAMEN`
5. 📚 Maps folder/file names to canonical module names
6. ✍️ Enriches each module with pre-authored 150-word French editorial metadata
7. 💾 Writes **`gi_database_final.json`** with:
   - `modules_metadata` — E-E-A-T compliant editorial records
   - `resources` — all files with real `drive_file_id`, `embed_url`, `download_url`

---

## Step 4 — Verify the output

```bash
python -c "
import json
with open('gi_database_final.json') as f:
    db = json.load(f)
print('Modules :', len(db['modules_metadata']))
print('Resources:', len(db['resources']))
# Show breakdown by semester
from collections import Counter
sems = Counter(r['semester'] for r in db['resources'])
for s, c in sorted(sems.items()):
    print(f'  {s}: {c} files')
"
```

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `google.auth.exceptions.DefaultCredentialsError` | Make sure `credentials.json` or `service_account.json` is in the script directory |
| `HttpError 403 insufficientPermissions` | The service account needs "Viewer" access to the Drive folders |
| `HttpError 404 File not found` | Folder IDs are correct — check that the folder is shared with the service account |
| `HttpError 429 rateLimitExceeded` | Increase `time.sleep(0.1)` to `time.sleep(0.5)` in `crawl_folder()` |
| Browser doesn't open for OAuth | Run with `flow.run_console()` instead of `run_local_server()` |
| `Token has been expired or revoked` | Delete `token.json` and re-run — a new browser flow will start |

---

## Output JSON structure

```json
{
  "_meta": { ... },
  "modules_metadata": [
    {
      "major": "Génie Informatique",
      "semester": "S3",
      "module_name": "Prog I (Langage C)",
      "description": "... 150 words ...",
      "key_exam_topics": ["...", "..."],
      "prerequisites": ["..."]
    }
  ],
  "resources": [
    {
      "major": "Génie Informatique",
      "semester": "S3",
      "academic_year": "2020-2021",
      "module": "Prog I (Langage C)",
      "category": "EXAMEN",
      "title": "Examen_C_2021.pdf",
      "drive_file_id": "1AbCdEf...",
      "embed_url": "https://drive.google.com/file/d/1AbCdEf.../preview",
      "download_url": "https://drive.google.com/uc?export=download&id=1AbCdEf..."
    }
  ]
}
```
