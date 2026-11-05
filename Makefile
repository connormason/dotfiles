#
# Makefile for Connor's dotfiles
#
# Auto-generated via `run.py makefile`
#
.PHONY: help list-hosts inventory-status update-inventory vault-decrypt vault-encrypt clean run-hooks pre prepare-hooks install-hooks uninstall-hooks makefile nas-provision doctor bootstrap stow render track-claude test

BRIGHT_GREEN := \033[0;92m
BRIGHT_WHITE := \033[0;97m
YELLOW := \033[0;33m
NC := \033[0m

help: ## Show this help message
	@echo "$(BRIGHT_GREEN)Runner script for Connor's dotfiles$(NC)"
	@echo ""
	@echo "$(BRIGHT_WHITE)Inventory:$(NC)"
	@echo "  $(YELLOW)list-hosts          $(NC) List available bootstrap targets from inventory"
	@echo "  $(YELLOW)inventory-status    $(NC) Display current status of inventory directory"
	@echo "  $(YELLOW)update-inventory    $(NC) Update inventory repo"
	@echo "  $(YELLOW)vault-decrypt       $(NC) Decrypt all inventory vault files for editing"
	@echo "  $(YELLOW)vault-encrypt       $(NC) Re-encrypt all inventory vault files after editing"
	@echo ""
	@echo "$(BRIGHT_WHITE)Codebase:$(NC)"
	@echo "  $(YELLOW)clean               $(NC) Remove all environments, build artifacts, and caches"
	@echo "  $(YELLOW)run-hooks           $(NC) Run prek hooks on modified or specified project files"
	@echo "  $(YELLOW)pre                 $(NC) Run prek (pre-commit) hooks on all project files"
	@echo "  $(YELLOW)prepare-hooks       $(NC) Prepare the environments of all prek hooks"
	@echo "  $(YELLOW)install-hooks       $(NC) Install prek git hook shims (overwrites any existing shims)"
	@echo "  $(YELLOW)uninstall-hooks     $(NC) Uninstall prek git hook shims"
	@echo "  $(YELLOW)makefile            $(NC) Generate Makefile from project management script commands [2m(run.py)[0m"
	@echo ""
	@echo "$(BRIGHT_WHITE)NAS:$(NC)"
	@echo "  $(YELLOW)nas-provision       $(NC) Provision the NAS with the Ansible playbook: system config, the stow engine, then services"
	@echo ""
	@echo "$(BRIGHT_WHITE)Dotfiles:$(NC)"
	@echo "  $(YELLOW)doctor              $(NC) Check tools, overlays, git version and hooks, links, rendered settings, and Brewfiles"
	@echo "  $(YELLOW)bootstrap           $(NC) Run the layered bootstrap stages (bootstrap/bootstrap.sh)"
	@echo "  $(YELLOW)stow                $(NC) Link stow packages from every layer into the home directory (stow.sh)"
	@echo "  $(YELLOW)render              $(NC) Render settings files from per-layer fragments (scripts/dotfiles/render.py)"
	@echo "  $(YELLOW)track-claude        $(NC) Ingest new ~/.claude agents, commands, skills, hooks, and rules into the repo"
	@echo "  $(YELLOW)test                $(NC) Run the test suite via uv (public-index wrapper)"
	@echo ""

# Inventory
list-hosts: ## List available bootstrap targets from inventory
	@python3 run.py list-hosts

inventory-status: ## Display current status of inventory directory
	@python3 run.py inventory-status

update-inventory: ## Update inventory repo
	@python3 run.py update-inventory

vault-decrypt: ## Decrypt all inventory vault files for editing
	@python3 run.py vault-decrypt

vault-encrypt: ## Re-encrypt all inventory vault files after editing
	@python3 run.py vault-encrypt

# Codebase
clean: ## Remove all environments, build artifacts, and caches
	@python3 run.py clean

run-hooks: ## Run prek hooks on modified or specified project files
	@python3 run.py run-hooks

pre: ## Run prek (pre-commit) hooks on all project files
	@python3 run.py pre

prepare-hooks: ## Prepare the environments of all prek hooks
	@python3 run.py prepare-hooks

install-hooks: ## Install prek git hook shims (overwrites any existing shims)
	@python3 run.py install-hooks

uninstall-hooks: ## Uninstall prek git hook shims
	@python3 run.py uninstall-hooks

makefile: ## Generate Makefile from project management script commands [2m(run.py)[0m
	@python3 run.py makefile

# NAS
nas-provision: ## Provision the NAS with the Ansible playbook: system config, the stow engine, then services
	@python3 run.py nas-provision

# Dotfiles
doctor: ## Check tools, overlays, git version and hooks, links, rendered settings, and Brewfiles
	@python3 run.py doctor

bootstrap: ## Run the layered bootstrap stages (bootstrap/bootstrap.sh)
	@python3 run.py bootstrap

stow: ## Link stow packages from every layer into the home directory (stow.sh)
	@python3 run.py stow

render: ## Render settings files from per-layer fragments (scripts/dotfiles/render.py)
	@python3 run.py render

track-claude: ## Ingest new ~/.claude agents, commands, skills, hooks, and rules into the repo
	@python3 run.py track-claude

test: ## Run the test suite via uv (public-index wrapper)
	@python3 run.py test
