# jenkins.autotests.cloud

Production-деплой Jenkins на том же хосте, что и [selenoid.autotests.cloud](https://selenoid.autotests.cloud): **https://jenkins.autotests.cloud**

| На сервере | Значение |
|------------|----------|
| URL | https://jenkins.autotests.cloud |
| Controller | `jenkins/jenkins:jdk21`, порт **8082** → UI |
| Agent port | **50000** |
| Compose | `/var/docker-compose-config/docker-compose.yml` |
| JENKINS_HOME | `/var/jenkins_home` (не трогаем при деплое) |
| Agents | 3× JDK21 + 3× Python3 (Docker) |

## Быстрый старт

| Действие | Как |
|----------|-----|
| **GitHub deploy** | Actions → [deploy](.github/workflows/deploy.yml) → Run workflow |
| **Nginx reload** | Actions → [nginx-reload](.github/workflows/nginx-reload.yml) |
| **Smoke** | `./deploy/smoke-remote.sh https://jenkins.autotests.cloud` |

Подробности: [`deploy/README.md`](deploy/README.md).

## Связь с Selenoid

Jenkins и Selenoid на **136.243.89.21** (8 vCPU, 31 GB RAM). Warm pool CI (будущее) — co-located: agent → `127.0.0.1:4444` / orchestrator `:9090`.

## Репозиторий

Скрипты деплоя живут здесь (по аналогии с [qa-guru/selenoid.autotests.cloud](https://github.com/qa-guru/selenoid.autotests.cloud)). Секреты agent'ов — только в `agents.env` на сервере, не в git.
