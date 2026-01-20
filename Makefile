#
# Makefile for Connor's dotfiles
#
# Auto-generated via `run.py makefile`
#
.PHONY: help list-hosts update-inventory install-uv install-hatch clean pre makefile

BRIGHT_GREEN := \033[0;92m
BRIGHT_WHITE := \033[0;97m
YELLOW := \033[0;33m
NC := \033[0m

help: ## Show this help message
	@echo "$(BRIGHT_GREEN)Runner script for Connor's dotfiles$(NC)"
	@echo ""
	@echo "$(BRIGHT_WHITE)Inventory:$(NC)"
	@echo "  $(YELLOW)list-hosts      $(NC) List available bootstrap targets from inventory"
	@echo "  $(YELLOW)update-inventory$(NC) Update inventory repo"
	@echo ""
	@echo "$(BRIGHT_WHITE)Tool Installation:$(NC)"
	@echo "  $(YELLOW)install-uv      $(NC) Install [95muv[0m Python project manager"
	@echo "  $(YELLOW)install-hatch   $(NC) Install [95mhatch[0m Python project manager"
	@echo ""
	@echo "$(BRIGHT_WHITE)Codebase:$(NC)"
	@echo "  $(YELLOW)clean           $(NC) Remove all environments, build artifacts, and caches"
	@echo "  $(YELLOW)pre             $(NC) Run pre-commit hooks on all project files"
	@echo "  $(YELLOW)makefile        $(NC) Generate Makefile from project management script commands [2m(run.py)[0m"
	@echo ""

# Inventory
list-hosts: ## List available bootstrap targets from inventory
	@python3 run.py list-hosts

update-inventory: ## Update inventory repo
	@python3 run.py update-inventory

# Tool Installation
install-uv: ## Install [95muv[0m Python project manager
	@python3 run.py install-uv

install-hatch: ## Install [95mhatch[0m Python project manager
	@python3 run.py install-hatch

# Codebase
clean: ## Remove all environments, build artifacts, and caches
	@python3 run.py clean

pre: ## Run pre-commit hooks on all project files
	@python3 run.py pre

makefile: ## Generate Makefile from project management script commands [2m(run.py)[0m
	@python3 run.py makefile
