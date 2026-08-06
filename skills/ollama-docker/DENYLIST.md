# Docker deny-list additions — rewrite or refuse, never run as-is

The base ollama-shell deny-list (`skills/ollama-shell/DENYLIST.md`) still
applies to every command string. ON TOP of it:

- `docker system prune` (any flags) — bulk cleanup is out of scope.
- `docker volume rm` / `docker volume prune` — deletes data volumes.
- `docker network rm` / `docker network prune`.
- `docker image prune` / `docker container prune` / `docker builder prune`.
- `docker rm -f` / `--force` on a RUNNING container (force-kills and removes in one step).
- `docker rmi -f` / `--force`.
- Batch delete/stop/kill of many containers at once: `docker rm $(docker ps -aq)`,
  `docker stop $(docker ps -q)`, `docker kill $(…)` — never draft the "everything" form.
- `docker compose down -v` / `--volumes` (drops named volumes = data loss) or `--rmi all`.
- `docker exec` that runs a destructive command INSIDE the container (`rm -rf`, `dd`,
  `mkfs`, `> /dev/sda`) — the base shell deny-list applies inside the container too.
- Container escape / host exposure the user did not explicitly ask for: `--privileged`,
  bind-mounting host root or system paths (`-v /:/…`), `--pid=host`, `--network=host`,
  `--cap-add=ALL`, `--security-opt seccomp=unconfined`.
- Mounting or reading credentials into a container: `~/.docker/config.json`, `~/.ssh`,
  `~/.aws`, `.env`, cloud metadata endpoints.
- `docker login` and anything that prints or stores registry credentials.

A command on this list is not "probably fine". Rewrite a narrow, safe version
yourself, or ask the user.
