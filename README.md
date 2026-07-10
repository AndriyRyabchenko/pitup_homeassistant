# PitUp — інтеграція для Home Assistant

Інформер стану вашої техніки з [PitUp](https://pitup.app) у Home Assistant:
скоро / протерміновано ТО, найближче обслуговування, пробіг — окремою сутністю
на кожну техніку.

## Встановлення (HACS)

1. HACS → **Integrations** → меню ⋮ → **Custom repositories**.
2. Додайте репозиторій `https://github.com/AndriyRyabchenko/pitup_homeassistant`,
   категорія **Integration**.
3. Знайдіть **PitUp** у списку та встановіть.
4. Перезапустіть Home Assistant.

### Вручну

Скопіюйте теку `custom_components/pitup` у `config/custom_components/` вашого HA
й перезапустіть.

## Налаштування

1. У PitUp: **Налаштування → Home Assistant → Згенерувати токен**, скопіюйте токен.
2. У Home Assistant: **Settings → Devices & Services → Add Integration → PitUp**.
3. Введіть адресу (`https://pitup.app`) і токен.

Створяться сутності:

- `sensor.pitup` — загальний стан парку (`ok` / `soon` / `overdue`), а в атрибутах —
  зведення по всій техніці (`vehicles`, `totals`).
- `sensor.pitup_<техніка>` — стан кожної техніки з деталями (пробіг, найближче ТО, список пунктів).

## Картка на панель

Додайте картку типу **Markdown** (див. `lovelace-card.yaml`):

```yaml
type: markdown
title: PitUp — техніка
content: |
  {% set vs = state_attr('sensor.pitup','vehicles') or [] %}
  {% for v in vs %}
  {% set dot = '🔴' if v.status=='overdue' else ('🟡' if v.status=='soon' else '🟢') %}
  ### {{ dot }} {{ v.title }}
  Пробіг: **{{ v.mileage }} {{ v.unit }}**{% if v.mileage_estimated %} (≈){% endif %}
  {% if v.next %}Найближче: **{{ v.next.name }}**{% endif %}
  {% endfor %}
```

## Опитування

Дані оновлюються раз на годину (`cloud_polling`).
