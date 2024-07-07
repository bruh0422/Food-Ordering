from flask import Flask, request, session, abort, render_template, redirect, url_for # 引入網頁框架

# 引入 Line Bot SDK
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import *
from linebot.v3.webhooks import *
from linebot.v3.messaging import *

# 引入自訂函式
from src.bot_core import *
from src.data_handler import *
from src.cache import action, web_session
from src.func import *

import re, datetime

# 取得環境變數
import os
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__) # 初始化 Flask
app.secret_key = os.urandom(24).hex()

# 初始化 Line Bot SDK
configuration = Configuration(access_token=os.getenv('channel_access_token'))
handler = WebhookHandler(os.getenv('channel_secret'))
with ApiClient(configuration) as api_client:
    line_bot_api = MessagingApi(api_client)

# 取得 root_url 和 port
root_url = os.getenv('root_url')
port = os.getenv('port')

@app.route("/callback", methods=['POST']) # 回應 Line Bot 的 POST 請求
def callback():
    signature = request.headers['X-Line-Signature']

    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        data_check()
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)

    return 'OK'

@handler.add(PostbackEvent) # 處理 PostbackEvent
def handle_postback(event: PostbackEvent):
    line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=event.source.user_id))

    messages = []

    if set_admin(event.source.user_id):
        messages.append(TextMessage(text='初始化管理員...'))

    data = parse_to_dict(event.postback.data)

    user, display_name = get_user(line_bot_api, event.source.user_id)
    role, role_display = get_role(user)

    if data['action'] == 'role_select': # 選擇身份
        if data['type'] == 'reset': # 管理者重置
            if user.user_id not in action['role']['reset']:
                action['role']['reset'].append(user.user_id)

            messages.append(TextMessage(text=f'📝輸入單個使用者 ID / 或輸入 all 來清除所有使用者的身份:'))
        else:
            if role != [] and role != ['admin']:
                messages.append(TextMessage(text=f'❌你目前的身份是「{role_display}」\n若要更改請洽詢管理員'))
            else:
                personnel_data = load_data('system', 'personnel.json')
                personnel_data[data["role"]].append(user.user_id)
                write_data(personnel_data, 'system', 'personnel.json')

                role, role_display = get_role(user)

                messages.append(TextMessage(text=f'✔️選擇成功\n你目前的身份為: {role_display}'))
    elif data['action'] == 'nickname': # 更改暱稱
        if data['type'] == 'change':
            if user.user_id not in action['nickname']['change']:
                action['nickname']['change'].append(user.user_id)

            messages.append(TextMessage(text=f'🏷️你目前的暱稱是: {get_nickname(user.user_id)}\n請輸入新暱稱: '))
        elif data['type'] == 'clear':
            nickname_data = load_data('system', 'nickname.json')
            if user.user_id in nickname_data:
                nickname_data.pop(user.user_id)
                write_data(nickname_data, 'system', 'nickname.json')

            messages.append(TextMessage(text='🏷️已清除你的暱稱'))
    elif data['action'] == 'show': # 顯示申請
        order_data = load_data('system', 'order.json')['pending']

        ui = {
            'type': 'carousel',
            'contents': []
        }

        if data['type'] == 'pending': # 教師介面待審核
            for order in order_data:
                for staff in order_data[order]['staff']:
                    if order_data[order]['staff'][staff] == -1:
                        current = staff
                        break

                if user.user_id == current:
                    ui['contents'].append(render_ui(
                        'pending',
                        status='pending',

                        store=order_data[order].get('store'),
                        item=order_data[order].get('item'),

                        class_name=order_data[order].get('class'),
                        user=order_data[order].get('user'),
                        pickup_time=order_data[order].get('pickup_time'),

                        staff=order_data[order].get('staff'),
                        order_id=order,

                        line_bot_api=line_bot_api,
                        stage=f'{list(order_data[order]["staff"].keys()).index(staff)+1} / {len(order_data[order]["staff"])}'
                    ))

            if ui['contents'] != []:
                messages.append(FlexMessage(altText='待審核申請', contents=FlexContainer.from_dict(ui)))
            else:
                messages.append(TextMessage(text='❌沒有待審核的申請'))
        elif data['type'] == 'waiting': # 學生介面待審核
            for order in order_data:
                for staff in order_data[order]['staff']:
                    if order_data[order]['staff'][staff] == -1:
                        current = staff
                        break

                ui['contents'].append(render_ui(
                    'pending',
                    status='waiting',

                    store=order_data[order].get('store'),
                    item=order_data[order].get('item'),

                    class_name=order_data[order].get('class'),
                    user=order_data[order].get('user'),
                    pickup_time=order_data[order].get('pickup_time'),

                    staff=order_data[order].get('staff'),
                    order_id=order,

                    line_bot_api=line_bot_api,
                    stage=f'{list(order_data[order]["staff"].keys()).index(staff)+1} / {len(order_data[order]["staff"])}'
                ))

            if ui['contents'] != []:
                messages.append(FlexMessage(altText='待審核申請', contents=FlexContainer.from_dict(ui)))
            else:
                messages.append(TextMessage(text='❌沒有待審核的申請'))
    elif data['action'] == 'verify': # 審核申請
        accept = True if data['type'] == 'accept' else False

        result = process_order(line_bot_api, data['order_id'], user.user_id, accept)

        if result:
            if accept:
                messages.append(TextMessage(text=f'✔️已核准申請'))
            else:
                if user.user_id not in action['verify']['reject']:
                    action['verify']['reject'][user.user_id] = data['order_id']
                messages.append(TextMessage(text='📝輸入拒絕原因:'))
        else:
            messages.append(TextMessage(text='❌你已經審核過這個訂單了!'))

    if messages == []:
        messages.append(TextMessage(text='❌這裡什麼都沒有 (程式可能出錯了)'))

    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))

@handler.add(MessageEvent, message=TextMessageContent) # 處理 MesaaageEvent
def handle_message(event: MessageEvent):
    line_bot_api.show_loading_animation(ShowLoadingAnimationRequest(chatId=event.source.user_id))

    messages = []

    if set_admin(event.source.user_id):
        messages.append(TextMessage(text='初始化管理員...'))

    user, display_name = get_user(line_bot_api, event.source.user_id)
    role, role_display = get_role(user)
    msg: str = event.message.text

    if role == [] or role == ['admin']: # 初次使用選擇身份
        messages.append(TextMessage(text='👋初次使用\n請選擇你的身份'))
        messages.append(FlexMessage(altText='選擇身份', contents=FlexContainer.from_dict(render_ui('role_select'))))
    else: # 若非初次使用
        if user.user_id in action['role']['reset']: # 如果正在更改暱稱
            if msg == 'all':
                personnel_data = load_data('system', 'personnel.json')
                personnel_data['staff'] = []
                personnel_data['student'] = []
                write_data(personnel_data, 'system', 'personnel.json')

                action['role']['reset'].remove(user.user_id)

                messages.append(TextMessage(text='✔️已清除所有使用者的身份'))
            else:
                target_user, target_display_name = get_user(line_bot_api, msg)

                if target_user is None:
                    messages.append(TextMessage(text='❌找不到此使用者'))
                else:
                    personnel_data = load_data('system', 'personnel.json')

                    if target_user.user_id in personnel_data['staff']: personnel_data['staff'].remove(target_user.user_id)
                    if target_user.user_id in personnel_data['student']: personnel_data['student'].remove(target_user.user_id)

                    write_data(personnel_data, 'system', 'personnel.json')

                    action['role']['reset'].remove(user.user_id)

                    messages.append(TextMessage(text=f'✔️已清除 {target_display_name}({target_user.user_id}) 的身份'))
        elif user.user_id in action['nickname']['change']: # 如果正在更改暱稱
            nickname_data = load_data('system', 'nickname.json')
            nickname_data[user.user_id] = msg
            write_data(nickname_data, 'system', 'nickname.json')

            action['nickname']['change'].remove(user.user_id)

            messages.append(TextMessage(text=f'🏷️暱稱已更改為: {msg}'))
        elif user.user_id in action['verify']['reject']: # 如果正在拒絕訂單
            order_id = action['verify']['reject'][user.user_id]
            process_order(line_bot_api, order_id, user.user_id, False, msg)

            action['verify']['reject'].pop(user.user_id)

            messages.append(TextMessage(text='📝已拒絕申請'))
        else: # 顯示功能選單
            messages.append(TextMessage(text=f'{role_display} {display_name}({user.user_id}) 您好👋'))

            ui = {
                'type': 'carousel',
                'contents': []
            }

            ui['contents'].append(render_ui('setting', uri=root_url))

            if 'admin' in role: ui['contents'].append(render_ui('admin'))
            if 'staff' in role: ui['contents'].append(render_ui('staff'))
            if 'student' in role:
                if user.user_id not in web_session: web_session[user.user_id] = os.urandom(24).hex()

                ui['contents'].append(render_ui(
                    'student',

                    uri=root_url,
                    uid=user.user_id,
                    token=web_session.get(user.user_id)
                ))

            messages.append(FlexMessage(altText='功能選單', contents=FlexContainer.from_dict(ui)))

    if messages == []:
        messages.append(TextMessage(text='❌這裡什麼都沒有 (程式可能出錯了)'))

    line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=messages))

@app.route('/')
def home():
    return 'OK'

@app.route('/personnel')
def personnel():
    personnel_data = load_data('system', 'personnel.json')

    render = lambda role: [render_name_and_id(line_bot_api, uid) for uid in personnel_data[role]]

    return render_template('personnel.html',
        admin='<br>'.join(render('admin')),
        staff='<br>'.join(render('staff')),
        student='<br>'.join(render('student'))
    )

@app.route('/new', methods=['GET', 'POST'])
def new():
    uid = request.args.get('uid')
    token = request.args.get('token')

    if request.method == 'GET':
        try:
            if uid is None: raise NameError
            if token is None or token != web_session.get(uid): raise PermissionError

            personnel_data = load_data('system', 'personnel.json')
            if uid not in personnel_data['student']: raise IndexError

            if not bool(re.findall(r'U[0-9a-f]{32}', uid)): raise ValueError
            user, display_name = get_user(line_bot_api, uid)

            if user is None: raise ApiException
        except NameError:
            return '❌網址格式錯誤 (未傳入 uid)<br>從 Line Bot 裡面直接點選 "送出新申請" 應該可以解決這個問題', 400
        except PermissionError:
            return '❌Invaild token', 400
        except IndexError:
            return '❌此使用者不是學生', 400
        except ValueError:
            return '❌抓取使用者時發生錯誤 (uid 格式錯誤)<br>uid 格式應該會像 "U[0-9a-f]{32}" (regular expression)', 400
        except ApiException:
            return '❌抓取使用者時發生錯誤 (無法從 Line API 抓取資料)<br>請檢查輸入的 uid 是否存在或者稍後再試', 400

        staff_list = []
        user_map = {}

        for u in load_data('system', 'personnel.json')['staff']:
            user, display_name = get_user(line_bot_api, u)

            if user is not None:
                staff_list.append(display_name)
                user_map[display_name] = u

        session['user_map'] = user_map

        return render_template('new.html',
            staff_list=staff_list
        )
    elif request.method == 'POST':
        messages = []

        if token is None or token != web_session.get(uid):
            return '❌Invaild token', 400
        else:
            web_session.pop(uid)

        form_data = request.form
        user_map = session.get('user_map')

        order_data = load_data('system', 'order.json')
        today_date = datetime.datetime.now(timezone).strftime('%Y%m%d')

        ids = list(order_data['finished']['accpeted'].keys()) + list(order_data['finished']['rejected'].keys()) + list(order_data['pending'].keys())

        exist_ids = sorted([i for i in ids if i.startswith(today_date)])

        if exist_ids:
            last_id = exist_ids[-1]
            last_number = int(last_id[-3:])
            new_number = last_number + 1
            order_id = today_date + str(new_number).zfill(3)
        else:
            order_id = today_date + '001'

        order_data['pending'][order_id] = {
            'line_id': uid,
            'time': int(datetime.datetime.now(timezone).timestamp()),

            'store': form_data.get('store'),
            'item': form_data.get('item'),

            'class': form_data.get('class'),
            'user': form_data.get('user'),
            'pickup_time': int(datetime.datetime.strptime(form_data.get('pickup_time'), '%Y-%m-%dT%H:%M').timestamp()),

            'staff': {user_map[s]: -1 for s in form_data.getlist('staff') if s != '-'}
        }
        write_data(order_data, 'system', 'order.json')

        process_order(line_bot_api, order_id, None, True)

        order_data = load_data('system', 'order.json')['pending']

        messages.append(FlexMessage(
            altText='已送出',
            contents=FlexContainer.from_dict(
                render_ui(
                    'pending',
                    status='sent',

                    store=order_data[order_id].get('store'),
                    item=order_data[order_id].get('item'),

                    class_name=order_data[order_id].get('class'),
                    user=order_data[order_id].get('user'),
                    pickup_time=order_data[order_id].get('pickup_time'),

                    staff=order_data[order_id].get('staff'),
                    order_id=order_id,

                    line_bot_api=line_bot_api
                )
            )
        ))

        if messages == []:
            messages.append(TextMessage(text='❌這裡什麼都沒有 (程式可能出錯了)'))

        line_bot_api.push_message(PushMessageRequest(to=uid, messages=messages))

        return redirect(url_for('new_success'))

@app.route('/new/success')
def new_success():
    return '''
        📨送出了!
        <script>
            alert('📨已成功送出!');
        </script>
    '''

@app.route('/github')
def github():
    return redirect('https://github.com/')

@app.route('/easteregg')
def easteregg():
    return redirect('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=port, debug=True)