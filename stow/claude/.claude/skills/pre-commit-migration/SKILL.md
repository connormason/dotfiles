---
name: pre-commit-migration
description: Migrate between pre-commit and prek git hook tools. Use when users explicitly ask to migrate from pre-commit to prek, convert their .pre-commit-config.yaml to prek.toml, switch from prek back to pre-commit, or compare the two tools for migration purposes.
---

# Pre-Commit Hook Migration

You are an expert at migrating between pre-commit and prek git hook tools.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [When This Skill Activates](#when-this-skill-activates)
- [Migration Workflow](#migration-workflow)
  - [1. Assess Current Configuration](#1-assess-current-configuration)
  - [2. Load Migration Reference](#2-load-migration-reference)
  - [3. Execute Migration](#3-execute-migration)
  - [4. Post-Migration Improvements](#4-post-migration-improvements)
- [Key Principles](#key-principles)

<!-- mdformat-toc end -->

## When This Skill Activates<a name="when-this-skill-activates"></a>

- User asks to migrate from pre-commit to prek (or vice versa)
- User asks to convert `.pre-commit-config.yaml` to `prek.toml`
- User asks about differences between pre-commit and prek for migration purposes

## Migration Workflow<a name="migration-workflow"></a>

### 1. Assess Current Configuration<a name="1-assess-current-configuration"></a>

Read the existing config file and check for:

- **Unsupported languages** (prek does not yet support: conda, coursier, dart, dotnet, perl, r)
- **Hazmat usage** (`pre-commit hazmat` is not implemented in prek)
- **CI/CD references** that will need updating

### 2. Load Migration Reference<a name="2-load-migration-reference"></a>

Read `references/migration-guide.md` for the complete compatibility matrix and step-by-step process.

### 3. Execute Migration<a name="3-execute-migration"></a>

Follow the migration guide steps. The typical flow for pre-commit → prek:

1. Verify prek is installed (`prek --version`)
2. Test existing YAML config with prek (`prek run --all-files`)
3. Reinstall git shims (`prek install -f`)
4. Optionally convert to TOML (`prek util yaml-to-toml` or manual conversion)
5. Optionally adopt prek-specific features (built-in hooks, `env`, `priority`, workspace mode)
6. Update CI/CD pipelines
7. Update team docs

### 4. Post-Migration Improvements<a name="4-post-migration-improvements"></a>

After migration, suggest prek-only features that could benefit the project:

- **Built-in hooks** (`repo: builtin`) — faster, zero-network, Rust-native implementations
- **`env` key** — set environment variables per hook
- **`priority`** — control execution order within a stage
- **Glob patterns** — use `{ glob: "*.py" }` instead of regex for file matching
- **Workspace mode** — for monorepos with multiple config files

## Key Principles<a name="key-principles"></a>

- **Test before switching**: Always verify the config works with the new tool before replacing git shims
- **Keep the old config during transition**: Don't delete `.pre-commit-config.yaml` until the team has confirmed prek
  works
- **Flag incompatibilities early**: Check for unsupported languages before starting migration
- **Update CI/CD**: Don't forget pipelines, Docker images, and GitHub Actions
