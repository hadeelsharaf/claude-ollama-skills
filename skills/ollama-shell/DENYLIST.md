# Deny-list — rewrite or refuse, never run as-is

This list applies to every drafted command string, from any skill or agent
that drafts shell, docker, or kubectl commands.

- Recursive delete outside the folder the user named (`rm -rf`, `Remove-Item -Recurse -Force`, `rd /s /q`, `del /f /s /q` on `~`, `/`, `$env:USERPROFILE`, `AppData`, wildcards at high levels)
- `git clean -fdx` / `-fd` (silently deletes untracked files — configs, .env, notes)
- Anything that discards uncommitted work: `git reset --hard`, `git checkout -- .`, `git restore .`, `git stash drop`, `git stash clear`
- Disk or partition operations (`format`, `diskpart`, `mkfs`, `dd`)
- Registry edits, `shutdown`, `reboot`, service stop/start
- Piping a download into a shell (`curl ... | sh`, `iwr ... | iex`)
- Reading or sending secrets: credential files (`.ssh`, `.aws`, tokens, browser profiles), `.env` files, or dumping env vars (`printenv`, `Get-ChildItem Env:`)
- Persistence: scheduled tasks (`schtasks /create`, `crontab`), editing `$PROFILE` or `.bashrc`
- `git push --force`, `git commit --no-verify`
- Mass permission changes (`chmod -R 777`, `icacls /reset /T`)
- Elevation the user did not explicitly request (`sudo`, `Start-Process -Verb RunAs`)
- Docker data / bulk destroyers: `docker system prune` (any flags), `docker volume rm` / `docker volume prune`, `docker network rm` / `docker network prune`, `docker image prune` / `docker container prune` / `docker builder prune`, `docker rm -f` / `docker rmi -f` (force), batch forms like `docker rm $(docker ps -aq)` / `docker stop $(docker ps -q)` / `docker kill $(...)`, and `docker compose down -v` / `--volumes` / `--rmi all`
- Docker host-escape the user did not ask for: `--privileged`, `--pid=host`, `--network=host`, `--cap-add=ALL`, `--security-opt seccomp=unconfined`, bind-mounting host root (`-v /:/...`); plus `docker login` or mounting credential files (`~/.docker/config.json`, `~/.ssh`, `~/.aws`, `.env`) into a container; and `docker exec` running a destructive command inside a container
- kubectl data / cluster destroyers: `kubectl delete namespace`, `kubectl delete pvc` / `pv`, `kubectl delete` with `--all` / `--all-namespaces` / `-l` / `--selector` / `--force --grace-period=0`, deleting a whole `deployment/statefulset/daemonset/job` the user did not name, any cluster-scoped write (nodes, PV, StorageClass, CRDs, ClusterRole/Binding, webhooks), `kubectl drain` / `cordon` / `taint`, `kubectl replace --force`, and `kubectl edit`
- kubectl reach / secret grabs: printing Secret values (`get secret -o yaml/jsonpath`, base64-decoding), `kubectl create token`, `kubectl cp` of token/secret paths, editing kubeconfig, widening access with `--kubeconfig` / `--token` / `--as` / `--context <other>`; `kubectl config use-context` / `set-context` / `delete-context` is the user's action, never drafted
- Git history / branch destroyers (beyond the ones above): `git rebase`, `git merge`, `git branch -D` / `-d`, `git tag -d`, `git push --force` / `--force-with-lease`, `git filter-branch`, `git reflog expire`, `git gc --prune=now`
- PowerShell aliases of Remove-Item with recursion: `rm -Recurse`, `rd -Recurse`, `ri -Recurse`, `del -Recurse`, `erase -Recurse`

A command on this list is not "probably fine". Rewrite a narrow, safe version
yourself, or ask the user.

## Review checklist (for any draft that needs review)

1. Deny-list check: does any part of the command match a line above? Rewrite
   a narrow, safe version yourself, or refuse.
2. Scope check: does the command touch ONLY what the user named? Wildcards or
   parent folders beyond the target = rewrite it yourself, narrower.
