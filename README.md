# jenkins.qa.guru

Production-деплой Jenkins на **Selectel Box2** (`89.248.193.83`, `ssh box2-ci`), не на Selenoid Box1: **https://jenkins.qa.guru**

| На сервере | Значение |
|------------|----------|
| URL | https://jenkins.qa.guru |
| Controller | `jenkins/jenkins:2.581-jdk21`, порт **8082** → UI |
| Agent port | **50000** |
| Compose | `/var/docker-compose-config/docker-compose.yml` |
| JENKINS_HOME | `/var/jenkins_home` (не трогаем при деплое) |
| Agents | 5× java-jdk21 + 5× python-python314 + 5× js-node24 (Docker, **Node 26.7.0** for allure-notifications 6.2.2) |

## Быстрый старт

| Действие | Как |
|----------|-----|
| **GitHub deploy** | Actions → [deploy](.github/workflows/deploy.yml) → Run workflow |
| **Nginx reload** | Actions → [nginx-reload](.github/workflows/nginx-reload.yml) |
| **Smoke** | `./deploy/smoke-remote.sh https://jenkins.qa.guru` |

Подробности: [`deploy/README.md`](deploy/README.md).

## Связь с Selenoid

Jenkins на **Selectel Box2** `89.248.193.83`. Selenoid на Box1 `89.248.192.30`. Warm pool CI (будущее) — agent → Box1 `:4444` / orchestrator `:9090` по сети, не co-located 127.0.0.1.

## Репозиторий

Скрипты деплоя живут здесь (по аналогии с [qa-guru/selenoid.qa.guru](https://github.com/qa-guru/selenoid.qa.guru)). Секреты agent'ов — только в `agents.env` на сервере, не в git.
