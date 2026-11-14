# Contributing

Thanks for your interest. Keepsake is developed in slices, described in [docs/build-prompt.md](docs/build-prompt.md).

## Ground rules

- Read the principles in [CLAUDE.md](CLAUDE.md). Changes that loosen any of them need an ADR in `docs/adr/` and the owner's agreement first.
- Never commit personal data: tokens, account names, device names, real save files or real game lists. Test fixtures are synthetic.
- UK English in UI text, docs, comments and commit messages. No em dashes or en dashes.
- Conventional commits, for example `feat(discovery): read shortcuts for all users`.
- All backend logic has tests. There is no CI: run `pnpm run check` and the tests for what you changed before opening a pull request, and say what you ran in the description.

## Setup

See [docs/dev-setup.md](docs/dev-setup.md). Enable the secret scan hook once per clone:

```
git config core.hooksPath .githooks
```

To block personal strings (game names, device names) from ever being committed, list them one per line in a local `.secret-scan-denylist` file. It is git-ignored.

## Licences

Only add code or data under licences compatible with BSD-3-Clause. GPL code, or code with an unconfirmed licence, needs the owner's agreement first.
