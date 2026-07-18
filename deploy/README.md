# Деплой jenkins.qa.guru

Jenkins controller + inbound agents через Docker Compose на prod-хосте.

## Текущая схема на сервере

```
/var/docker-compose-config/
  docker-compose.yml
  agents.env              ← секреты (не в git)
  jdk21-agent/Dockerfile
  python3-agent/Dockerfile
  bin/sync-nginx.sh

/var/jenkins_home/         ← данные Jenkins (volume, сохраняется)
```

| Сервис | Образ | Порты |
|--------|-------|-------|
| jenkins | `jenkins/jenkins:jdk21` | 8082→8080, 50000 |
| jdk21-jenkins-agent-{1,2,3} | `jdk21-jenkins-agent-ext` | internal |
| python3-jenkins-agent-{1,2,3} | `python3-jenkins-agent-ext` | internal |

Nginx: `/etc/nginx/sites-available/jenkins` → `127.0.0.1:8082`.

---

## Первый раз (bootstrap)

На сервере **от root**:

```bash
# из клона qa-guru/jenkins.qa.guru
sudo DEPLOY_USER=selenoid ./deploy/bootstrap.sh
```

Миграция секретов из старого compose (один раз):

```bash
sudo bash deploy/migrate-agents-env.sh
# или вручную: cp deploy/agents.env.example → /var/docker-compose-config/agents.env
```

```bash
sudo chown selenoid:docker /var/docker-compose-config/agents.env
sudo chmod 600 /var/docker-compose-config/agents.env
```

---

## Ручной деплой

```bash
# as selenoid
./deploy/deploy.sh
```

Обновляет compose и Dockerfiles, `docker compose build`, `up -d`. **`/var/jenkins_home` не удаляется.**

---

## GitHub Actions

Workflow [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml):

| Триггер | Когда |
|---------|-------|
| `workflow_dispatch` | Actions → deploy → Run workflow |
| `repository_dispatch: deploy-jenkins` | Вызов из внешнего CI |

### Environment `jenkins-production`

Можно переиспользовать secrets от Selenoid (тот же хост и пользователь `selenoid`):

| Secret | Fallback | Описание |
|--------|----------|----------|
| `JENKINS_DEPLOY_HOST` | `SELENOID_DEPLOY_HOST` | `136.243.89.21` |
| `JENKINS_DEPLOY_USER` | `SELENOID_DEPLOY_USER` | `selenoid` |
| `JENKINS_DEPLOY_KEY` | `SELENOID_DEPLOY_KEY` | SSH private key |

| Variable | Default | Описание |
|----------|---------|----------|
| `JENKINS_CONFIG_DIR` | `/var/docker-compose-config` | Каталог compose |
| `JENKINS_PUBLIC_URL` | `https://jenkins.qa.guru` | Smoke test |

Workflow inputs:

- `jenkins_image` — override `JENKINS_IMAGE` в `agents.env`
- `sync_nginx` — применить `nginx-jenkins.conf` (proxy на `127.0.0.1:8082`)

### Secrets agent'ов

**Не хранить в GitHub.** Файл `/var/docker-compose-config/agents.env` создаётся один раз на сервере (`migrate-agents-env.sh` или вручную).

---

## Nginx

Справочный конфиг: [`nginx-jenkins.conf`](nginx-jenkins.conf) — proxy на `127.0.0.1:8082` (вместо публичного IP в legacy-конфиге).

```bash
sudo NGINX_CONF_SRC=./deploy/nginx-jenkins.conf ./deploy/sync-nginx.sh
```

---

## Проверка

```bash
./deploy/smoke-remote.sh https://jenkins.qa.guru
curl -sf http://127.0.0.1:8082/login -o /dev/null && echo OK
docker compose -f /var/docker-compose-config/docker-compose.yml ps
```

---

## Безопасность

- Agent secrets вынесены из `docker-compose.yml` в `agents.env` (chmod 600).
- Не коммитить `agents.env` и не логировать secrets в CI.
- При ротации secret в Jenkins UI — обновить `agents.env` и `docker compose up -d`.
