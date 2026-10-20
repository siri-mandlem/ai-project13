from functools import wraps

from flask import g, jsonify, session

from backend.extensions import db
from backend.models import User


def current_user() -> User | None:
    user_id = session.get("user_id")
    if user_id is None:
        return None
    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        session.clear()
        return None
    return user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"error": "Authentication is required."}), 401
        g.current_user = user
        return view(*args, **kwargs)

    return wrapped


def roles_required(*roles: str):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if g.current_user.role not in roles:
                return jsonify({"error": "You do not have permission for this action."}), 403
            return view(*args, **kwargs)

        return wrapped

    return decorate
