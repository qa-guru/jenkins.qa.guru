# Деплой jenkins.qa.guru

Jenkins controller + inbound agents через Docker Compose на prod-хосте.

## Текущая схема на сервере

```
/var/docker-compose-config/
  docker-compose.yml
  agents.env              ← секреты (не в git)
  java-jdk21-agent/Dockerfile
  python-python314-agent/Dockerfile
  js-node24-agent/Dockerfile
  qa-guru/send-allure-telegram.sh   ← baked into agents → /opt/qa-guru/bin/
  qa-guru/allure-notifications.version  ← pin (= docs/allure-notifications/VERSION)
  bin/sync-nginx.sh

/var/jenkins_home/         ← данные Jenkins (volume, сохраняется)
```

| Сервис | Образ | Порты |
|--------|-------|-------|
| jenkins | `jenkins/jenkins:jdk21` | **`127.0.0.1:8082`→8080**, **`127.0.0.1:50000`** (не `0.0.0.0`) |
| java-jdk21-jenkins-agent-{1..5} | `java-jdk21-jenkins-agent-ext` | internal |
| python-python314-jenkins-agent-{1..5} | `python-python314-jenkins-agent-ext` | internal |
| js-node24-jenkins-agent-{1..5} | `js-node24-jenkins-agent-ext` | internal |

Nginx: `/etc/nginx/sites-available/jenkins` → `127.0.0.1:8082`.

**Security canon (2026-08-10):** `disableSignup=true`; matrix **`Hudson.Administer` только у `admin`** (не `authenticated`); публичный HTTP только nginx → `127.0.0.1:8082`. Re-apply: `../dev/scripts/harden-jenkins-security.sh`.

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

Signup (captcha off): `limit_req` on `GET /signup` (30r/m burst 20) and `POST /securityRealm/createAccount` (6r/m burst 8) → **429**. Zones are at the top of this file (`http{}` via `sites-enabled`).

```bash
sudo NGINX_CONF_SRC=./deploy/nginx-jenkins.conf ./deploy/sync-nginx.sh
```

Единственный Allure-specific блок — redirect `…/allure3/(awesome|dashboard)/` → `index.html`:
навигация **внутри** отчёта (корневая страница Allure 3 линкует подкаталоги), плагин на них
отвечает 500. Публикуемые ссылки идут сразу на `index.html` и этого правила не касаются — ADR 010.

---

## Allure notifications на агентах

`qa-guru/` — SSOT-копия из `jenkins-qa-guru-home/dev/` (обновляется `apply-jenkins-ssot.sh bake`),
запекается в образы агентов в `/opt/qa-guru/`:

| Файл | Назначение |
|------|------------|
| `send-allure-telegram.sh` | post-build отправка (jar 4.x для A2, CLI 6.x для A3) |
| `render-allure-notifications-config.sh` | build step: шаблон → `notifications/config.json` + URL contract |
| `allure3.json.tmpl` · `allure2.json.tmpl` | общий конфиг allure-notifications на все стеки |
| `allure-notifications.version` · `allure-notifications-jar-a2.version` | version pins |

---

## Проверка

```bash
./deploy/smoke-remote.sh https://jenkins.qa.guru   # + smoke-allure-jenkins-urls.sh (URL contract, ADR 010)
curl -sf http://127.0.0.1:8082/login -o /dev/null && echo OK
docker compose -f /var/docker-compose-config/docker-compose.yml ps
```

---

## Безопасность

- Agent secrets вынесены из `docker-compose.yml` в `agents.env` (chmod 600).
- Не коммитить `agents.env` и не логировать secrets в CI.
- При ротации secret в Jenkins UI — обновить `agents.env` и `docker compose up -d`.
