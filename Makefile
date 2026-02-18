.PHONY: build test lint fmt typecheck checkall clean install upgrade

build:
	uv build

test:
	uv run pytest

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests
	uv run ruff check --fix src tests

typecheck:
	uv run pyright src

checkall: fmt lint typecheck test

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pyright" -exec rm -rf {} + 2>/dev/null || true

install:
	uv pip install -e .

install-skill:
	mkdir -p ~/.claude/skills/cc-tmux
	cp -r skill/cc-tmux/* ~/.claude/skills/cc-tmux/
	@echo "Skill installed to ~/.claude/skills/cc-tmux/"

upgrade:
	uv tool upgrade cctmux --reinstall
	cctmux install-skill
