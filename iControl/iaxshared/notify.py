import requests

def notify(target, message, button_title, button_url, priority=3):
    try:
        url = f'https://ntfy.sh/{target}'
        headers = {
            'Title': button_title,
            'Click': button_url,
            'Priority': priority,  # Priority from -2 (lowest) to 5 (highest)
        }
        response = requests.post(url, data=message.encode('utf-8'), headers=headers)
        response.raise_for_status()
    except Exception as e:
        print(f'Error sending notification: {e}')