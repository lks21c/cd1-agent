# Git Commit & Push

Commit all changes and push to remote repository.

**Usage**: `/gcp [commit message]`

**Argument**: $ARGUMENTS

## Instructions

1. **Check git status**:
   ```bash
   git status
   ```

2. **If no changes**, report "No changes to commit" and exit.

3. **If changes exist**:
   - Stage all changes:
     ```bash
     git add -A
     ```

   - Create commit with provided message (or generate one):
     - If `$ARGUMENTS` is provided: use it as commit message
     - If no message provided: analyze the staged changes and generate an appropriate conventional commit message

   - Commit:
     ```bash
     git commit -m "message here"
     ```

   - Push to remote:
     ```bash
     git push
     ```

4. **Report results**:
   - Files changed
   - Commit hash
   - Branch pushed to
   - Remote URL

## Commit Message Guidelines

If generating a commit message:
- Use conventional commits format: `type(scope): description`
- Types: feat, fix, docs, style, refactor, test, chore
- Keep description under 72 characters
- Be specific about what changed

## Output Format

```
Committed: <short hash>
Branch: <branch name>
Message: <commit message>
Pushed to: <remote/branch>
```
