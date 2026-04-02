#!/usr/bin/env bash
set -euo pipefail

# Get latest release tag
latest=$(gh release list --limit 1 --json tagName --jq '.[0].tagName' 2>/dev/null || echo "")

if [[ -z "$latest" ]]; then
  next="v0.1.0"
else
  # Strip leading 'v' and split into parts
  version="${latest#v}"
  major="${version%%.*}"
  rest="${version#*.}"
  minor="${rest%%.*}"
  patch="${rest#*.}"

  if [[ "$patch" -ge 9 ]]; then
    minor=$((minor + 1))
    patch=0
  else
    patch=$((patch + 1))
  fi

  next="v${major}.${minor}.${patch}"
fi

echo "Creating release $next..."

gh release create "$next" \
  --title "PR Agent $next" \
  --notes "## Installation

\`\`\`bash
pip install git+https://github.com/andrewchaa/pr-agent.git
\`\`\`

Or with pipx (recommended for CLI tools):

\`\`\`bash
pipx install git+https://github.com/andrewchaa/pr-agent.git
\`\`\`

## Requirements
- Python 3.10+
- GitHub Copilot subscription
- GitHub CLI (\`gh\`)"

echo "Done! Release $next is live."
