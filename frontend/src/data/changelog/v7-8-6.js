export default {
  "version": "v7.8.6",
  "date": "2026-05-25",
  "sortKey": "2026-05-25T00:00:09Z",
  "title": "Hotfix: blank pages",
  "items": [
    "Navbar.jsx was re-exporting SITE_VERSION from version.js but not importing it locally, so the JSX reference threw a ReferenceError and crashed every page that mounts the navbar. Now imports and re-exports."
  ]
}
