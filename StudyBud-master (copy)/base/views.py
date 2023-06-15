from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.db.models import Q
from django.contrib.auth import authenticate, login, logout
from .models import Room, Topic, Message, User, RoomInvite, RoomPermission
from .forms import RoomForm, UserForm, MyUserCreationForm
import random
import time
import re
from datetime import datetime, timedelta

# Create your views here.

# rooms = [
#     {'id': 1, 'name': 'Lets learn python!'},
#     {'id': 2, 'name': 'Design with me'},
#     {'id': 3, 'name': 'Frontend developers'},
# ]


def loginPage(request):
    page = 'login'
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        email = request.POST.get('email').lower()
        password = request.POST.get('password')

        try:
            user = User.objects.get(email=email)
        except:
            messages.error(request, 'User does not exist')

        user = authenticate(request, email=email, password=password)

        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Username OR password does not exit')

    context = {'page': page}
    return render(request, 'base/login_register.html', context)


def logoutUser(request):
    logout(request)
    return redirect('home')


def registerPage(request):
    form = MyUserCreationForm()

    if request.method == 'POST':
        form = MyUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.username = user.username.lower()
            user.save()
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'An error occurred during registration' + str(form.errors))

    return render(request, 'base/login_register.html', {'form': form})


def home(request):
    q = request.GET.get('q') if request.GET.get('q') != None else ''

    user_id = request.user.id or -1
    permissioned_room_ids = list(RoomPermission.objects.raw(f"SELECT id, room_id FROM base_roompermission WHERE user_id = {user_id}"))
    permissioned_room_ids = [t.room_id for t in permissioned_room_ids]

    rooms = Room.objects.filter(
        (Q(topic__name__icontains=q) |
        Q(name__icontains=q) |
        Q(description__icontains=q)) & (
            Q(public=True) | 
            Q(id__in = permissioned_room_ids)
        ) 
    )

    topics = [room.topic for room in rooms]
    room_count = rooms.count()
    room_messages = Message.objects.filter(
        Q(room__topic__name__icontains=q) & Q(room__in = rooms))[0:3]

    context = {'rooms': rooms, 'topics': topics, 'room_messages' : room_messages,
               'room_count': room_count}
    return render(request, 'base/home.html', context)


def room(request, pk):

    user_id = request.user.id or -1
    permissioned_room_ids = list(RoomPermission.objects.raw(f"SELECT id, room_id FROM base_roompermission WHERE user_id = {user_id}"))
    permissioned_room_ids = [t.room_id for t in permissioned_room_ids]

    room = Room.objects.filter(Q(id=pk) & (Q(public=True) | Q(id__in=permissioned_room_ids)))
    if len(room) != 1:
        return HttpResponse('This room does not exist or you do not have permission to view it')
    room = room[0]

    participants = room.participants.all()

    if request.method == 'POST':
        Message.objects.create(
            user=request.user,
            room=room,
            body=request.POST.get('body')
        )
        room.participants.add(request.user)
        return redirect('room', pk=room.id)

    context = {'room': room,
               'participants': participants}
    return render(request, 'base/room.html', context)

def getMessages(request, pk):
    user_id = request.user.id or -1
    permissioned_room_ids = list(RoomPermission.objects.raw(f"SELECT id, room_id FROM base_roompermission WHERE user_id = {user_id}"))
    permissioned_room_ids = [t.room_id for t in permissioned_room_ids]
    if Room.objects.filter(Q(id=pk) & (Q(public=True) | Q(id__in=permissioned_room_ids))).count() != 1:
        return HttpResponse('This room does not exist or you do not have permission to view it')

    hashtag = request.GET.get('hashtag') if request.GET.get('hashtag') != None else ''
    query = f"SELECT base_message.id, avatar, username, body, created FROM base_message LEFT JOIN base_user ON base_message.user_id = base_user.id WHERE room_id = {pk}"
    if hashtag:
        query = query + f" AND base_message.body LIKE '%%#{hashtag}%%'"
    room_messages = list(Message.objects.raw(query))
    for i, message in enumerate(room_messages):
        created = message.created.strftime("%b %d %Y, %I:%M %p")
        #replace between quotations
        message.body = re.sub(r'\"(.*?)\"', r'\\"\1\\"', message.body)
        room_messages[i] = "{" + f'"avatar":\'{message.avatar}\', "username":\'{message.username}\', "body":\'{message.body}\', "created":\'{created}\'' + "}"
    return JsonResponse({'room_messages': list(room_messages)})


def userProfile(request, pk):
    user_id = request.user.id or -1
    permissioned_room_ids = list(RoomPermission.objects.raw(f"SELECT id, room_id FROM base_roompermission WHERE user_id = {user_id}"))
    permissioned_room_ids = [t.room_id for t in permissioned_room_ids]

    user = User.objects.get(id=pk)
    rooms = user.room_set.filter(Q(id__in=permissioned_room_ids) | Q(public=True))
    room_messages = user.message_set.filter(Q(room_id__in=permissioned_room_ids) | Q(room__public=True))
    topics = [room.topic for room in rooms]
    context = {'user': user, 'rooms': rooms,
               'room_messages': room_messages, 'topics': topics}
    return render(request, 'base/profile.html', context)


def createRoom(request):
    form = RoomForm()
    topics = Topic.objects.all()
    if request.method == 'POST':
        topic_name = request.POST.get('topic')
        topic, created = Topic.objects.get_or_create(name=topic_name)

        room = Room.objects.create(
            host=request.user,
            topic=topic,
            name=request.POST.get('name'),
            description=request.POST.get('description'),
            public=request.POST.get('public') and True or False,
        )
        RoomPermission.objects.create(user=request.user, room=room)
        return redirect('home')

    context = {'form': form, 'topics': topics}
    return render(request, 'base/room_form.html', context)


def updateRoom(request, pk):
    room = Room.objects.get(id=pk)
    form = RoomForm(instance=room)
    topics = Topic.objects.all()
    if request.user != room.host:
        return HttpResponse('Your are not allowed here!!')

    if request.method == 'POST':
        topic_name = request.POST.get('topic')
        topic, created = Topic.objects.get_or_create(name=topic_name)
        room.name = request.POST.get('name')
        room.topic = topic
        room.description = request.POST.get('description')
        room.save()
        return redirect('home')

    context = {'form': form, 'topics': topics, 'room': room}
    return render(request, 'base/room_form.html', context)


def deleteRoom(request, pk):
    room = Room.objects.get(id=pk)

    if request.method == 'POST':
        room.delete()
        return redirect('home')
    return render(request, 'base/delete.html', {'obj': room})


def getInviteLink(request, pk):
    user_id = request.user.id or -1
    permissioned_room_ids = list(RoomPermission.objects.raw(f"SELECT id, room_id FROM base_roompermission WHERE user_id = {user_id}"))
    permissioned_room_ids = [t.room_id for t in permissioned_room_ids]
    if Room.objects.filter(Q(id=pk) & (Q(public=True) | Q(id__in=permissioned_room_ids))).count() != 1:
        return HttpResponse('This room does not exist or you do not have permission to view it')


    random.seed(int(time.time()))
    key = random.randint(100, 999)
    expires = datetime.now() + timedelta(hours=24)
    invite = RoomInvite.objects.get_or_create(room_id=int(pk), key=key, expires=expires)[0]
    return JsonResponse({"room":invite.room_id, "key":invite.key, "expires":expires})

def acceptInvite(request, pk):
    q = request.GET.get('key') if request.GET.get('key') != None else ''
    invite = RoomInvite.objects.get(room_id=pk, key=int(q), expires__gte=datetime.now())
    if invite:
        RoomPermission.objects.get_or_create(room_id=pk, user_id=request.user.id)
        return redirect('room', pk=pk)
    else:
        return HttpResponse("Invalid invite link")

def deleteMessage(request, pk):
    message = Message.objects.get(id=pk)

    if request.user != message.user:
        return HttpResponse('Your are not allowed here!!')

    if request.method == 'POST':
        message.delete()
        return redirect('home')
    return render(request, 'base/delete.html', {'obj': message})


def updateUser(request):
    user = request.user
    form = UserForm(instance=user)

    if request.method == 'POST':
        form = UserForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            return redirect('user-profile', pk=user.id)

    return render(request, 'base/update-user.html', {'form': form})


def topicsPage(request):
    q = request.GET.get('q') if request.GET.get('q') != None else ''

    user_id = request.user.id or -1
    permissioned_room_ids = list(RoomPermission.objects.raw(f"SELECT id, room_id FROM base_roompermission WHERE user_id = {user_id}"))
    permissioned_room_ids = [t.room_id for t in permissioned_room_ids]

    rooms = Room.objects.filter(
        Q(topic__name__icontains=q) & (
            Q(public=True) | 
            Q(id__in = permissioned_room_ids)
        ) 
    )

    topics = [room.topic for room in rooms]
    return render(request, 'base/topics.html', {'topics': topics})


def activityPage(request):

    user_id = request.user.id or -1
    permissioned_room_ids = list(RoomPermission.objects.raw(f"SELECT id, room_id FROM base_roompermission WHERE user_id = {user_id}"))
    permissioned_room_ids = [t.room_id for t in permissioned_room_ids]

    room_messages = Message.objects.filter(Q(room_id__in=permissioned_room_ids) | Q(room__public=True)).order_by('-created')[:100]
    return render(request, 'base/activity.html', {'room_messages': room_messages})
