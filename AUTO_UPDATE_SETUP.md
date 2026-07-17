# One-time automatic update setup

The updater runs every day at 04:00 HKT and can also be started from the
repository's Actions tab.

## 1. Create a Google service account

1. Open Google Cloud Console and create or select a project.
2. Enable **Google Drive API**.
3. Open **IAM & Admin → Service Accounts** and create a service account.
4. Create a JSON key and download it.

The service account needs no project role. Drive access is granted only by
sharing the selected folders in the next step.

## 2. Share the four scan folders as Viewer

Copy the service account email from the JSON (`client_email`) and share these
folders with it as **Viewer**:

- NTK
- Generated Products
- Comparisons
- `data_booklets`

Do not share the whole Drive.

## 3. Save the JSON as a GitHub secret

1. Open the repository's **Settings → Secrets and variables → Actions**.
2. Select **New repository secret**.
3. Name: `GOOGLE_SERVICE_ACCOUNT_JSON`
4. Value: paste the entire downloaded JSON file.

Never upload the JSON file to the repository.

## 4. Run the first update

Open **Actions → Update Drive index → Run workflow**. After it finishes,
`resources.json` appears in the repository and GitHub Pages refreshes.

The indexer uses Drive metadata-only permission. It scans only the four folder
IDs above and excludes backend/source/validation/legacy paths. The public site
contains titles and Drive links; Drive permissions still protect file content.
