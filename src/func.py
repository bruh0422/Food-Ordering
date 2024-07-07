from linebot.v3.messaging import *

from src.data_handler import load_data, write_data

from src.bot_core import *
from src.data_handler import *

import datetime

def render_ui(name: str, **kwargs) -> dict:
    ui = load_data('ui', f'{name}.json')

    if name == 'setting':
        ui['footer']['contents'][0]['action']['uri'] = ui['footer']['contents'][0]['action']['uri'].replace('{uri}', kwargs['uri'])
    elif name == 'student':
        ui['footer']['contents'][0]['action']['uri'] = ui['footer']['contents'][0]['action']['uri'].replace('{uri}', kwargs['uri'])
        ui['footer']['contents'][0]['action']['uri'] = ui['footer']['contents'][0]['action']['uri'].replace('{uid}', kwargs['uid'])
        ui['footer']['contents'][0]['action']['uri'] = ui['footer']['contents'][0]['action']['uri'].replace('{token}', kwargs['token'])
    elif name == 'pending':
        ui['body']['contents'][2]['text'] = kwargs['store']
        ui['body']['contents'][3]['text'] = kwargs['item']

        ui['body']['contents'][5]['contents'][0]['contents'][1]['text'] = kwargs['class_name']
        ui['body']['contents'][5]['contents'][1]['contents'][1]['text'] = kwargs['user']
        ui['body']['contents'][5]['contents'][2]['contents'][1]['text'] = datetime.datetime.fromtimestamp(kwargs['pickup_time'], timezone).strftime('%Y-%m-%d %H:%M')

        staff = ' → '.join([get_user(kwargs['line_bot_api'], s)[1] for s in kwargs['staff']])
        ui['body']['contents'][5]['contents'][4]['contents'][1]['text'] = staff

        ui['body']['contents'][7]['contents'][1]['text'] = kwargs['order_id']

        if kwargs['status'] == 'sent':
            ui['body']['contents'][0]['text'] = '已送出'
            ui['body']['contents'][0]['color'] = '#0080ff'
            ui['body']['contents'][1]['text'] = '📨等待審核'
        elif kwargs['status'] in ['waiting', 'pending']:
            ui['body']['contents'][0]['text'] = '待審核'
            ui['body']['contents'][0]['color'] = '#ffa500'
            ui['body']['contents'][1]['text'] = f'階段 {kwargs["stage"]}'

            if kwargs['status'] == 'pending':
                ui['footer'] = {
                    'type': 'box',
                    'layout': 'horizontal',
                    'contents': [
                        {
                            'type': 'button',
                            'action': {
                                'type': 'postback',
                                'label': '核准',
                                'data': f'action=verify&type=accept&order_id={kwargs["order_id"]}'
                            },
                            'style': 'primary',
                            'margin': 'sm'
                        },
                        {
                            'type': 'button',
                            'action': {
                                'type': 'postback',
                                'label': '拒絕',
                                'data': f'action=verify&type=reject&order_id={kwargs["order_id"]}'
                            },
                            'style': 'secondary',
                            'margin': 'sm'
                        }
                    ]
                }
        elif kwargs['status'] == 'accept':
            ui['body']['contents'][0]['text'] = '通過'
            ui['body']['contents'][0]['color'] = '#1db446'
            ui['body']['contents'][1]['text'] = '🎉恭喜! 你的申請已通過!'
        elif kwargs['status'] == 'reject':
            ui['body']['contents'][0]['text'] = '未通過'
            ui['body']['contents'][0]['color'] = '#ff0000'
            ui['body']['contents'][1]['text'] = f'❌抱歉! 你的申請未通過!'
            ui['body']['contents'].insert(
                2,
                {
                    'type': 'text',
                    'text': f'原因: {kwargs["reason"]}',
                    'color': '#aaaaaa',
                    'size': 'sm'
                }
            )

    return ui

def process_order(line_bot_api: MessagingApi, order_id: str, uid: str | None, accept: bool, reason: str=None) -> bool:
    messages = []

    order_data = load_data('system', 'order.json')
    try:
        order: dict = order_data['pending'][order_id]
    except KeyError:
        return False

    for staff in order['staff']:
        if order['staff'][staff] == -1:
            current = staff
            break

    if uid is not None:
        if uid != current: return False

    if accept:
        if uid is not None:
            order['staff'][current] = int(datetime.datetime.now(timezone).timestamp())
            write_data(order_data, 'system', 'order.json')

        if -1 in order['staff'].values():
            for staff in order['staff']:
                if order['staff'][staff] == -1:
                    next_staff = staff
                    break

            ui = render_ui(
                'pending',
                status='pending',

                store=order.get('store'),
                item=order.get('item'),

                class_name=order.get('class'),
                user=order.get('user'),
                pickup_time=order.get('pickup_time'),

                staff=order.get('staff'),
                order_id=order_id,

                line_bot_api=line_bot_api,
                stage=f'{list(order["staff"].keys()).index(staff)+1} / {len(order["staff"])}'
            )

            messages.append(FlexMessage(altText='新的申請審核', contents=FlexContainer.from_dict(ui)))

            line_bot_api.push_message(PushMessageRequest(to=next_staff, messages=messages))
        else:
            order_data['finished']['accepted'][order_id] = order_data['pending'].pop(order_id)
            write_data(order_data, 'system', 'order.json')

            ui = render_ui(
                'pending',
                status='accept',

                store=order.get('store'),
                item=order.get('item'),

                class_name=order.get('class'),
                user=order.get('user'),
                pickup_time=order.get('pickup_time'),

                staff=order.get('staff'),
                order_id=order_id,

                line_bot_api=line_bot_api
            )

            messages.append(FlexMessage(altText='申請通過', contents=FlexContainer.from_dict(ui)))

            line_bot_api.push_message(PushMessageRequest(to=order['line_id'], messages=messages))
    else:
        if reason is not None:
            order['staff'][current] = int(datetime.datetime.now(timezone).timestamp())
            write_data(order_data, 'system', 'order.json')

            order['reason'] = reason
            order_data['finished']['rejected'][order_id] = order_data['pending'].pop(order_id)
            write_data(order_data, 'system', 'order.json')

            ui = render_ui(
                'pending',
                status='reject',

                store=order.get('store'),
                item=order.get('item'),

                class_name=order.get('class'),
                user=order.get('user'),
                pickup_time=order.get('pickup_time'),

                staff=order.get('staff'),
                order_id=order_id,

                line_bot_api=line_bot_api,
                reason=reason
            )

            messages.append(FlexMessage(altText='申請未通過', contents=FlexContainer.from_dict(ui)))

            line_bot_api.push_message(PushMessageRequest(to=order['line_id'], messages=messages))

    return True