import asyncio
import websockets
import json
import base64

connected_clients = {}
rooms = {
    'General': {
        'creator': 'System',
        'users': set(),
        'history': []
    }
}


async def broadcast(message, room='General', exclude=None):
    for client_name, client_info in connected_clients.items():
        if client_info['room'] == room and client_info['websocket'] != exclude:
            try:
                await client_info['websocket'].send(message)
            except websockets.exceptions.ConnectionClosed:
                print(f"Failed to send message to {client_name}")
                if client_name in connected_clients:
                    del connected_clients[client_name]
                    if client_info['room'] in rooms:
                        rooms[client_info['room']]['users'].discard(client_name)
                        await update_user_list(client_info['room'])


async def update_user_list(room='General'):
    if room == 'General':
        # For General room, send all online users
        user_list = list(connected_clients.keys())
    else:
        # For other rooms, send only users in the current room
        user_list = [name for name, info in connected_clients.items() if info['room'] == room]

    await broadcast(json.dumps({
        'type': 'userList',
        'users': user_list
    }), room)


async def update_room_list():
    room_info = {'General': rooms['General']}
    room_info.update({name: info for name, info in rooms.items() if name != 'General'})
    await broadcast(json.dumps({
        'type': 'roomList',
        'rooms': {name: {'creator': info['creator']} for name, info in room_info.items()}
    }))


async def handle_client(websocket, path):
    client_name = None
    client_room = 'General'

    try:
        async for message in websocket:
            data = json.loads(message)

            if data['type'] == 'setName':
                client_name = data['name']
                client_room = data.get('room', 'General')
                connected_clients[client_name] = {'websocket': websocket, 'room': client_room}
                rooms[client_room]['users'].add(client_name)

                for msg in rooms[client_room]['history']:
                    await websocket.send(json.dumps(msg))

                await update_user_list(client_room)
                await update_room_list()

            elif data['type'] == 'message':
                if client_name:
                    message_data = {
                        'type': 'message',
                        'name': client_name,
                        'content': data['content'],
                        'room': data['room']
                    }
                    rooms[data['room']]['history'].append(message_data)
                    await broadcast(json.dumps(message_data), data['room'])

            elif data['type'] == 'file':
                if client_name:
                    file_data = {
                        'type': 'file',
                        'name': client_name,
                        'content': data['content'],
                        'fileName': data['fileName'],
                        'fileType': data['fileType'],
                        'room': data['room']
                    }
                    rooms[data['room']]['history'].append(file_data)
                    await broadcast(json.dumps(file_data), data['room'])

            elif data['type'] == 'createRoom':
                new_room = data['name']
                if new_room not in rooms:
                    rooms[new_room] = {
                        'creator': client_name,
                        'users': set(),
                        'history': []
                    }
                    await update_room_list()

            elif data['type'] == 'joinRoom':
                old_room = client_room
                new_room = data['name']

                if new_room in rooms and new_room != old_room:
                    rooms[old_room]['users'].remove(client_name)
                    rooms[new_room]['users'].add(client_name)
                    connected_clients[client_name]['room'] = new_room
                    client_room = new_room

                    for msg in rooms[new_room]['history']:
                        await websocket.send(json.dumps(msg))

                    await update_user_list(old_room)
                    await update_user_list(new_room)

    except websockets.exceptions.ConnectionClosed:
        print(f"Client connection closed unexpectedly")
    finally:
        if client_name:
            if client_name in connected_clients:
                del connected_clients[client_name]
            if client_room in rooms:
                rooms[client_room]['users'].discard(client_name)
                await update_user_list(client_room)

                if len(rooms[client_room]['users']) == 0 and client_room != 'General':
                    del rooms[client_room]
                    await update_room_list()


async def main():
    server = await websockets.serve(handle_client, "172.23.72.235", 8765)
    print("WebSocket server started on ws://172.23.72.235:8765")
    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())