# Systemd User Service Setup

This directory contains the systemd unit file to run the App Reviews Flask application as a user service (non-root).

## Installation

1. Create the systemd user directory if it doesn't exist:
   ```bash
   mkdir -p ~/.config/systemd/user
   ```

2. Link the service file to the systemd user directory:
   ```bash
   ln -sf <PROJECT_ROOT>/systemd/app-reviews.service ~/.config/systemd/user/
   ```

3. Reload the systemd user daemon:
   ```bash
   systemctl --user daemon-reload
   ```

4. Enable and start the service:
   ```bash
   systemctl --user enable --now app-reviews.service
   ```

## Management

- **Check Status**:
  ```bash
  systemctl --user status app-reviews.service
  ```

- **Stop Service**:
  ```bash
  systemctl --user stop app-reviews.service
  ```

- **Restart Service**:
  ```bash
  systemctl --user restart app-reviews.service
  ```

- **View Logs**:
  ```bash
  journalctl --user -u app-reviews.service -f
  ```

## Notes
- The service runs in `production` mode using Gunicorn.
- It listens on port `5952` by default (configurable via `.env` or the service file).
- It uses the Python environment at `python`.
