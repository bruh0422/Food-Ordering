from linebot.v3.exceptions import *
from linebot.v3.webhooks import *
from linebot.v3.messaging import *

from src.data_handler import load_data, write_data

import datetime

timezone = datetime.timezone(datetime.timedelta(hours=8))

def set_admin(user_id: str) -> bool | None:
    personnel_data = load_data('system', 'personnel.json')

    if personnel_data['admin'] == []:
        personnel_data['admin'].append(user_id)
        write_data(personnel_data, 'system', 'personnel.json')
        return True

def get_user(line_bot_api: MessagingApi, uid: str) -> tuple[UserProfileResponse | None, str | None]:
    try:
        user = line_bot_api.get_profile(uid)
    except ApiException:
        user = None

    nickname = get_nickname(uid)

    display_name = None

    if user is not None:
        if nickname != '':
            display_name = nickname
        else:
            display_name = user.display_name

    return user, display_name

def get_nickname(uid: str) -> str:
    nickname_data = load_data('system', 'nickname.json')
    return nickname_data.get(uid, '')

def get_role(user: UserProfileResponse) -> tuple[list, str]:
    personnel_data = load_data('system', 'personnel.json')

    users = personnel_data['staff'] + personnel_data['student']
    if users.count(user.user_id) > 1:
        personnel_data['student'].remove(user.user_id)
        write_data(personnel_data, 'system', 'personnel.json')

    role = [r for r in personnel_data if user.user_id in personnel_data[r]]

    table = {
        'admin': '管理員',
        'staff': '審核者',
        'student': '學生'
    }

    role_display = "兼".join([table[r] for r in role])

    return role, role_display

def render_name_and_id(line_bot_api: MessagingApi, uid: str):
    user, display_name = get_user(line_bot_api, uid)

    return f'{display_name}({uid})'