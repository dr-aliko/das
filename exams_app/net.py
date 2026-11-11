WRONG_PENALTY = 0.25


def calculate_net(correct, wrong):
    return round((correct or 0) - (wrong or 0) * WRONG_PENALTY, 2)


def total_net(results):
    return round(sum(calculate_net(r.correct_answers, r.wrong_answers) for r in results), 2)


def with_net_field(update_fields, field_name):
    if update_fields is None:
        return None
    return set(update_fields) | {field_name}
