# SSHFerry Docs

<div align="center">
  <p>
    <img src="https://img.shields.io/badge/Docs-Maintained-0F172A?style=for-the-badge" alt="Maintained docs">
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="Backend docs">
    <img src="https://img.shields.io/badge/Frontend-React%20%2B%20Vite-2563EB?style=for-the-badge&logo=react&logoColor=white" alt="Frontend docs">
    <img src="https://img.shields.io/badge/Language-English-111827?style=for-the-badge" alt="English docs">
  </p>

  <p>
    Implementation-facing documentation for the current SSHFerry codebase.
  </p>

  <p>
    <a href="README_zh.md">中文</a> |
    <b>English</b>
  </p>

  <p>
    <a href="#document-map">Document Map</a> |
    <a href="#recommended-reading-paths">Reading Paths</a> |
    <a href="#scope-rules">Scope Rules</a>
  </p>
</div>

## Document Map

### Core References

- 🛠️ [Backend Overview](backend/BACKEND_OVERVIEW.md)
- 📘 [Frontend Build Guide](frontend/FRONTEND_BUILD.md)
- 🔌 [Frontend API Guide](frontend/FRONTEND_API.md)
- 🎨 [Frontend Design Guide](frontend/FRONTEND_DESIGN.md)

### Additional Notes

- 🇨🇳 [Transfer Rules Alignment Note (Chinese)](backend/TRANSFER_RULES_zh.md)

## Recommended Reading Paths

### For general contributors

1. 🧭 Start from the product-facing root [README.md](../README.md)
2. 🛠️ Read the [Backend Overview](backend/BACKEND_OVERVIEW.md)
3. 🔌 Open the API guide only if you need endpoint-level details

### For frontend work

1. 📘 Read the [Frontend Build Guide](frontend/FRONTEND_BUILD.md)
2. 🔌 Continue with the [Frontend API Guide](frontend/FRONTEND_API.md)
3. 🎨 Finish with the [Frontend Design Guide](frontend/FRONTEND_DESIGN.md)

### For backend-oriented work

1. 🛠️ Read the [Backend Overview](backend/BACKEND_OVERVIEW.md)
2. 🔌 Cross-check behavior against current route and service code
3. 🇨🇳 Review the transfer-rules note when protocol behavior needs historical context

## How To Use This Folder

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🧭 Start Here</h3>
      <p>Use the root README files for product-level positioning, setup, and recommended run paths.</p>
    </td>
    <td width="33%" valign="top">
      <h3>🛠️ Use Docs For Implementation</h3>
      <p>This folder is for architecture, API, build, and integration details that would clutter the main README.</p>
    </td>
    <td width="33%" valign="top">
      <h3>🔍 Trust Code First</h3>
      <p>If a document and current implementation disagree, treat the codebase as the source of truth until docs are updated.</p>
    </td>
  </tr>
</table>

## Scope Rules

- 📌 Root `README.md` and `README_zh.md` are the product-facing entry points.
- 📚 `docs/` contains implementation-oriented reference material.
- 🔍 API behavior should follow the current backend code first, then these docs.
- 🧹 Historical drafts, stale migration notes, and duplicate assets are intentionally excluded here.

## Maintenance Notes

- Update this index when a maintained document is added, removed, or renamed.
- Prefer linking to the smallest useful document instead of repeating the same explanation across files.
- If a doc becomes aspirational instead of descriptive, trim it or rewrite it.
