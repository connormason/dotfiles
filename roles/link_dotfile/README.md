# Link Dotfile Role

## Purpose

A reusable utility role for safely creating symbolic links from dotfiles in the repository to their target locations
in the user's home directory. This role handles validation, backup, and idempotent linking operations.

## What It Does

1. **Validates inputs**:
   - Ensures required variables are defined
   - Verifies source file exists before linking

2. **Handles existing files**:
   - Backs up existing non-symlink files with timestamp
   - Removes incorrect symlinks
   - Preserves correct existing symlinks (idempotent)

3. **Creates symlinks**:
   - Creates parent directories as needed
   - Links source to destination
   - Reports when files are already correctly linked

## Required Variables

This role must be called with two required variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `link_dotfile_src` | Absolute path to source file in dotfiles repo | `{{ dotfiles_home }}/roles/git/files/gitconfig` |
| `link_dotfile_dst` | Absolute path to destination (target location) | `{{ user_home }}/.gitconfig` |

## Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `dotfile_dir_mode` | Permissions for created parent directories | `omit` (uses default) |

## Usage Examples

### Basic Usage

Include the role with required variables:

```yaml
- name: Link git config
  ansible.builtin.include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_home }}/roles/git/files/gitconfig"
    link_dotfile_dst: "{{ user_home }}/.gitconfig"
```

### Link Multiple Files in a Loop

```yaml
- name: Link shell dotfiles
  ansible.builtin.include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_home }}/roles/shell/files/{{ item }}"
    link_dotfile_dst: "{{ user_home }}/.{{ item }}"
  loop:
    - zshrc
    - zprofile
    - zshenv
```

### Specify Directory Permissions

```yaml
- name: Link config with custom directory mode
  ansible.builtin.include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_home }}/roles/app/files/config.yml"
    link_dotfile_dst: "{{ user_home }}/.config/app/config.yml"
    dotfile_dir_mode: "0700"
```

## Behavior Details

### Validation Phase

1. Asserts that both `link_dotfile_src` and `link_dotfile_dst` are defined
2. Checks if source file exists
3. Fails if source file does not exist

### Linking Logic

The role follows this decision tree:

```
1. Check destination file status
   ├─ Does not exist
   │  └─ Create parent directory → Create symlink
   │
   ├─ Exists as regular file (not symlink)
   │  └─ Backup file → Create symlink
   │
   ├─ Exists as symlink pointing to correct source
   │  └─ Skip (already correct) ✓
   │
   └─ Exists as symlink pointing to wrong source
      └─ Remove symlink → Create new symlink
```

### Backup Behavior

When a non-symlink file exists at the destination:

- Creates backup: `<destination>.backup_YYYYMMDDHHMMSS`
- Example: `.zshrc.backup_20250219143022`
- Original file is moved (not copied)
- Symlink is then created

### Idempotency

- If symlink already points to correct source: No changes made
- Debug message confirms: "✅ [destination] is already correctly linked to [source]"
- Supports Ansible's `--check` mode for dry runs

## Error Handling

### Missing Required Variables

```
fatal: Missing required vars for link_dotfile.
       You must define both `link_dotfile_src` and `link_dotfile_dst`.
```

### Source File Does Not Exist

```
fatal: Source file '[path]' does not exist
```

## Dependencies

None. This is a standalone utility role.

## Debug Output

The role provides helpful debug messages:

```
TASK [Output link_dotfile action]
ok: [localhost] => {
    "msg": "Linking dotfile /path/to/source to /path/to/destination"
}

TASK [Dotfile already correctly linked]
ok: [localhost] => {
    "msg": "✅ /path/to/destination is already correctly linked to /path/to/source"
}
```

## Best Practices

### Always Use Absolute Paths

```yaml
# Good
link_dotfile_src: "{{ dotfiles_home }}/roles/git/files/gitconfig"

# Bad
link_dotfile_src: ../git/files/gitconfig
```

### Use Variable Substitution

```yaml
# Good
link_dotfile_dst: "{{ user_home }}/.config/app/config.yml"

# Bad
link_dotfile_dst: /Users/username/.config/app/config.yml
```

### Loop When Linking Multiple Files

```yaml
# Good
- include_role:
    name: roles/link_dotfile
  vars:
    link_dotfile_src: "{{ dotfiles_home }}/files/{{ item }}"
    link_dotfile_dst: "{{ user_home }}/.{{ item }}"
  loop: [file1, file2, file3]

# Bad (repetitive)
- include_role: ...  # file1
- include_role: ...  # file2
- include_role: ...  # file3
```

## Testing

### Verify Symlink

```bash
ls -la ~/.config/starship.toml
# Output: lrwxr-xr-x  1 user  staff  ... -> /path/to/dotfiles/roles/starship/files/starship.toml
```

### Verify Backup Created

```bash
ls -la ~/.zshrc*
# Output:
# lrwxr-xr-x  1 user  staff  ... .zshrc -> /path/to/dotfiles/roles/shell/files/zshrc
# -rw-r--r--  1 user  staff  ... .zshrc.backup_20250219143022
```
