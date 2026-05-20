#!/bin/zsh
# litra_dispatch.sh
# SSH command gatekeeper for Logitech Litra Glow control.
# Invoked exclusively via the restrict,command= directive in
# /Users/homeassistant/.ssh/authorized_keys — never called directly.
# Whitelists specific litra commands; rejects everything else with exit 1.
# Security model and integration details: guides/litra_glow.md

LITRA="/opt/homebrew/bin/litra"
RUN_AS="<your_username>"

# Composite apply: "litra apply [state=on|off] [brightness=N] [temperature=N]"
# All args optional. Order of operations: turn on -> brightness -> temperature -> turn off.
apply_composite() {
  local state="" brightness="" temperature=""
  for arg in "$@"; do
    case "$arg" in
      state=on)         state="on" ;;
      state=off)        state="off" ;;
      brightness=*)     brightness="${arg#brightness=}" ;;
      temperature=*)    temperature="${arg#temperature=}" ;;
      *) echo "Bad apply arg: $arg" >&2; exit 1 ;;
    esac
  done

  # Validate numerics if provided
  if [[ -n "$brightness" && ! "$brightness" =~ ^[0-9]+$ ]]; then
    echo "Invalid brightness: $brightness" >&2; exit 1
  fi
  if [[ -n "$temperature" && ! "$temperature" =~ ^[0-9]+$ ]]; then
    echo "Invalid temperature: $temperature" >&2; exit 1
  fi

  # Turn on first so brightness/temp apply to a powered device
  if [[ "$state" == "on" ]]; then
    sudo -u "$RUN_AS" "$LITRA" on || exit 1
  fi
  if [[ -n "$brightness" ]]; then
    sudo -u "$RUN_AS" "$LITRA" brightness --percentage "$brightness" || exit 1
  fi
  if [[ -n "$temperature" ]]; then
    sudo -u "$RUN_AS" "$LITRA" temperature --value "$temperature" || exit 1
  fi
  # Turn off last so brightness/temp changes are applied before powering down
  if [[ "$state" == "off" ]]; then
    sudo -u "$RUN_AS" "$LITRA" off || exit 1
  fi
}

case "$SSH_ORIGINAL_COMMAND" in
  "litra apply "*)
    REST="${SSH_ORIGINAL_COMMAND#litra apply }"
    apply_composite ${=REST} ;;
  "litra on")                   sudo -u "$RUN_AS" "$LITRA" on ;;
  "litra off")                  sudo -u "$RUN_AS" "$LITRA" off ;;
  "litra toggle")               sudo -u "$RUN_AS" "$LITRA" toggle ;;
  "litra brightness --value "*)
    LEVEL="${SSH_ORIGINAL_COMMAND#litra brightness --value }"
    sudo -u "$RUN_AS" "$LITRA" brightness --value "$LEVEL" ;;
  "litra brightness --percentage "*)
    PCT="${SSH_ORIGINAL_COMMAND#litra brightness --percentage }"
    sudo -u "$RUN_AS" "$LITRA" brightness --percentage "$PCT" ;;
  "litra brightness-up --value "*)
    LEVEL="${SSH_ORIGINAL_COMMAND#litra brightness-up --value }"
    sudo -u "$RUN_AS" "$LITRA" brightness-up --value "$LEVEL" ;;
  "litra brightness-up --percentage "*)
    PCT="${SSH_ORIGINAL_COMMAND#litra brightness-up --percentage }"
    sudo -u "$RUN_AS" "$LITRA" brightness-up --percentage "$PCT" ;;
  "litra brightness-down --value "*)
    LEVEL="${SSH_ORIGINAL_COMMAND#litra brightness-down --value }"
    sudo -u "$RUN_AS" "$LITRA" brightness-down --value "$LEVEL" ;;
  "litra brightness-down --percentage "*)
    PCT="${SSH_ORIGINAL_COMMAND#litra brightness-down --percentage }"
    sudo -u "$RUN_AS" "$LITRA" brightness-down --percentage "$PCT" ;;
  "litra temperature --value "*)
    TEMP="${SSH_ORIGINAL_COMMAND#litra temperature --value }"
    sudo -u "$RUN_AS" "$LITRA" temperature --value "$TEMP" ;;
  "litra temperature-up --value "*)
    TEMP="${SSH_ORIGINAL_COMMAND#litra temperature-up --value }"
    sudo -u "$RUN_AS" "$LITRA" temperature-up --value "$TEMP" ;;
  "litra temperature-down --value "*)
    TEMP="${SSH_ORIGINAL_COMMAND#litra temperature-down --value }"
    sudo -u "$RUN_AS" "$LITRA" temperature-down --value "$TEMP" ;;
  "litra devices --json")         sudo -u "$RUN_AS" "$LITRA" devices --json ;;
  *) echo "Unauthorized command" >&2; exit 1 ;;
esac
