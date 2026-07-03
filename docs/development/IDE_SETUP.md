# IDE Setup Guide for Agent Grey

This guide helps you configure popular IDEs to use flake8 linting automatically during development.

## Pre-requisites

Ensure flake8 is installed in your development environment:

```bash
# In Docker (recommended)
docker compose exec web pip install flake8

# Or locally
pip install flake8
```

## VS Code (Visual Studio Code)

### 1. Install Python Extension

Install the official Python extension by Microsoft from the VS Code marketplace.

### 2. Configure Flake8

Add to your `.vscode/settings.json` (create if it doesn't exist):

```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.linting.flake8Path": "${workspaceFolder}/venv/bin/flake8",
  "python.linting.flake8Args": [
    "--config=${workspaceFolder}/.flake8"
  ],
  "python.linting.lintOnSave": true,
  "python.formatting.provider": "black",
  "python.formatting.blackPath": "${workspaceFolder}/venv/bin/black",
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  },
  "files.exclude": {
    "**/__pycache__": true,
    "**/*.pyc": true,
    ".pytest_cache": true,
    ".mypy_cache": true
  }
}
```

### 3. Docker Integration (Optional)

If using Docker for development:

```json
{
  "python.defaultInterpreterPath": "/usr/local/bin/python",
  "python.linting.flake8Path": "/usr/local/bin/flake8",
  "remote.containers.defaultExtensions": [
    "ms-python.python"
  ]
}
```

## PyCharm / IntelliJ IDEA

### 1. Enable Flake8

1. Go to **Settings/Preferences** → **Tools** → **External Tools**
2. Click **+** to add a new tool
3. Configure:
   - **Name**: Flake8
   - **Program**: `$ProjectFileDir$/venv/bin/flake8` (or `flake8` if in PATH)
   - **Arguments**: `--config=$ProjectFileDir$/.flake8 $FilePath$`
   - **Working directory**: `$ProjectFileDir$`

### 2. Configure File Watcher (Automatic Linting)

1. Go to **Settings** → **Tools** → **File Watchers**
2. Click **+** → **Custom**
3. Configure:
   - **Name**: Flake8 Auto-Lint
   - **File type**: Python
   - **Scope**: Project Files
   - **Program**: `$ProjectFileDir$/venv/bin/flake8`
   - **Arguments**: `--config=$ProjectFileDir$/.flake8 $FilePath$`
   - **Output paths to refresh**: `$FilePath$`
   - **Working directory**: `$ProjectFileDir$`
   - **Auto-save edited files**: ✓

### 3. Keyboard Shortcut

1. Go to **Settings** → **Keymap**
2. Search for "Flake8" (under External Tools)
3. Right-click → **Add Keyboard Shortcut**
4. Suggested: `Ctrl+Shift+F8` or `Cmd+Shift+F8`

## Sublime Text

### 1. Install Package Control

If not already installed, follow instructions at https://packagecontrol.io/installation

### 2. Install SublimeLinter and Flake8

1. `Ctrl+Shift+P` (or `Cmd+Shift+P`) → **Package Control: Install Package**
2. Install **SublimeLinter**
3. Install **SublimeLinter-flake8**

### 3. Configure

Create/edit `Preferences → Package Settings → SublimeLinter → Settings`:

```json
{
  "linters": {
    "flake8": {
      "executable": "${folder}/venv/bin/flake8",
      "args": ["--config=${folder}/.flake8"],
      "python": "${folder}/venv/bin/python"
    }
  },
  "lint_mode": "background",
  "show_marks_in_minimap": true
}
```

## Vim / Neovim

### Using ALE (Asynchronous Lint Engine)

Add to your `.vimrc` or `init.vim`:

```vim
" Install vim-plug if not already installed
call plug#begin('~/.vim/plugged')
Plug 'dense-analysis/ale'
call plug#end()

" Configure ALE for Python
let g:ale_linters = {
\   'python': ['flake8'],
\}
let g:ale_python_flake8_executable = 'venv/bin/flake8'
let g:ale_python_flake8_options = '--config=.flake8'
let g:ale_lint_on_save = 1
let g:ale_lint_on_text_changed = 'never'
let g:ale_lint_on_insert_leave = 0
```

### Using coc.nvim

Install coc-pyright and configure in `:CocConfig`:

```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.linting.flake8Path": "./venv/bin/flake8"
}
```

## Pre-commit Hooks (All IDEs)

The best way to ensure code quality is to install pre-commit hooks that run automatically before each commit:

```bash
# Install pre-commit
pip install pre-commit

# Install the git hooks
pre-commit install

# Run manually on all files (optional)
pre-commit run --all-files

# Run manual checks (full flake8, Django checks)
pre-commit run --all-files --hook-stage manual
```

### Bypassing Hooks (When Needed)

If you need to commit without running hooks (use sparingly):

```bash
git commit --no-verify -m "Your commit message"
```

## Troubleshooting

### Flake8 not found

**Issue**: IDE can't find flake8 executable

**Solutions**:
1. Ensure flake8 is installed: `pip install flake8`
2. Use full path: `/path/to/venv/bin/flake8`
3. For Docker: `docker compose exec web which flake8`

### Wrong Python interpreter

**Issue**: IDE using system Python instead of project virtualenv

**Solutions**:
1. **VS Code**: `Ctrl+Shift+P` → "Python: Select Interpreter" → Choose `./venv/bin/python`
2. **PyCharm**: Settings → Project → Python Interpreter → Add Local Interpreter
3. **Command line**: `source venv/bin/activate` (Unix) or `venv\Scripts\activate` (Windows)

### Flake8 config not respected

**Issue**: IDE shows different errors than command-line flake8

**Solutions**:
1. Verify config path in IDE settings points to `.flake8`
2. Check working directory is project root
3. Clear IDE cache and restart

### Too many warnings

**Issue**: Flake8 shows hundreds of warnings in legacy code

**Solutions**:
1. Use pre-commit critical-only checks: Configured in `.pre-commit-config.yaml`
2. Add exclusions to `.flake8` per-file-ignores
3. Focus on files you're actively working on

## Verification

Test your setup:

```bash
# Should show linting errors if any exist
flake8 apps/core/logging_config.py

# Should respect .flake8 config
flake8

# Should run pre-commit hooks
git commit -m "test" --allow-empty
```

## Quick Reference

| IDE | Lint Command | Config Location |
|-----|-------------|-----------------|
| VS Code | Automatic on save | `.vscode/settings.json` |
| PyCharm | File Watchers | Settings → Tools → File Watchers |
| Sublime | Background | Package Settings → SublimeLinter |
| Vim/Neovim | ALE / CoC | `.vimrc` / `:CocConfig` |

## Next Steps

1. ✅ Install flake8 in your environment
2. ✅ Configure your IDE using instructions above
3. ✅ Install pre-commit hooks
4. ✅ Test with a small change
5. ✅ Verify linting works before committing

---

**Questions?** Check the [Agent Grey CLAUDE.md](../CLAUDE.md) for project-specific guidelines.
