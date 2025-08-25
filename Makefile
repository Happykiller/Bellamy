# Makefile - run trading bot in PROD mode

PYTHON := python
BOT    := app.bot

export MODE=prod

# Commandes principales
price:
	$(PYTHON) -m $(BOT) price

balance:
	$(PYTHON) -m $(BOT) balance

indicators:
	$(PYTHON) -m $(BOT) indicators

buy:
	@if [ -z "$(amount)" ]; then \
		echo "❌ Usage: make buy amount=0.001"; \
		exit 1; \
	fi
	$(PYTHON) -m $(BOT) buy $(amount)

sell:
	@if [ -z "$(amount)" ]; then \
		echo "❌ Usage: make sell amount=0.001"; \
		exit 1; \
	fi
	$(PYTHON) -m $(BOT) sell $(amount)
