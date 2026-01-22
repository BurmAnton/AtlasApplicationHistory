from django import template


register = template.Library()

@register.filter
def has_groups(user, group_names):
    """Проверяет наличие пользователя в любой из указанных групп"""
    groups = group_names.split(',')
    return user.groups.filter(name__in=groups).exists()


@register.filter
def compact_history(history_qs):
    """
    Убирает дублирующиеся записи истории статусов.

    Правила:
    - история берётся в хронологическом порядке (от старых к новым);
    - если подряд идут записи с одинаковой парой (atlas_status, rr_status),
      оставляем только САМУЮ РАННЮЮ запись из этой серии;
    - итоговый список возвращаем в том же (возрастающем) порядке.

    Таким образом:
    - при полностью неизменном статусе будет показан только самый первый срез;
    - при повторяющихся импортах без изменений промежуточные срезы не отображаются.
    """
    # На вход могут передать уже materialized queryset или RelatedManager
    try:
        items = list(history_qs.order_by("snapshot_dt"))
    except Exception:  # noqa: BLE001
        items = list(history_qs)
        items.sort(key=lambda h: h.snapshot_dt)

    result = []
    last_pair = None

    for h in items:
        pair = (h.atlas_status, h.rr_status)
        if pair == last_pair:
            # Ничего не изменилось относительно предыдущей записи — пропускаем
            continue
        result.append(h)
        last_pair = pair

    return result



