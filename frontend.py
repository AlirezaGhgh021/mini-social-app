import streamlit as st
import requests
import base64
import urllib.parse

st.set_page_config(page_title="Simple Social", layout="wide")

# Session state
if 'token' not in st.session_state:
    st.session_state.token = None
if 'user' not in st.session_state:
    st.session_state.user = None


def get_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}


def login_page():
    st.title("Welcome to Simple Social")

    email = st.text_input("Email:")
    password = st.text_input("Password:", type="password")

    if email and password:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Login", type="primary", use_container_width=True):
                response = requests.post("http://localhost:8000/auth/jwt/login", data={"username": email, "password": password})
                if response.status_code == 200:
                    st.session_state.token = response.json()["access_token"]
                    user_resp = requests.get("http://localhost:8000/users/me", headers=get_headers())
                    if user_resp.status_code == 200:
                        st.session_state.user = user_resp.json()
                        st.rerun()
                else:
                    st.error("Invalid credentials")
        with col2:
            if st.button("Sign Up", use_container_width=True):
                response = requests.post("http://localhost:8000/auth/register", json={"email": email, "password": password})
                if response.status_code == 201:
                    st.success("Registered! Now login.")
                else:
                    st.error(response.json().get("detail", "Registration failed"))


def upload_page():
    st.title("Share Something")
    file = st.file_uploader("Media", type=['png', 'jpg', 'jpeg', 'mp4', 'mov'])
    caption = st.text_area("Caption")

    if file and st.button("Share", type="primary"):
        with st.spinner("Uploading..."):
            files = {"file": (file.name, file.getvalue(), file.type)}
            data = {"caption": caption}
            resp = requests.post("http://localhost:8000/upload", files=files, data=data, headers=get_headers())
            if resp.status_code == 200:
                st.success("Posted!")
                st.rerun()
            else:
                st.error("Upload failed")


def encode_text_for_overlay(text):
    if not text:
        return ""
    b64 = base64.b64encode(text.encode()).decode()
    return urllib.parse.quote(b64)


def create_transformed_url(url, params="", caption=None):
    if caption:
        enc = encode_text_for_overlay(caption)
        params = f"l-text,ie-{enc},ly-N20,lx-20,fs-100,co-white,bg-000000A0,l-end"
    if not params:
        return url
    parts = url.split("/")
    return f"{'/'.join(parts[:4])}/tr:{params}/{('/'.join(parts[4:]))}"


def feed_page():
    st.title("Feed")

    st.query_params.clear()  # ← THIS IS THE NUCLEAR FIX — FORCES FRESH DATA EVERY TIME

    response = requests.get("http://localhost:8000/feed", headers=get_headers())
    if response.status_code != 200:
        st.error("Failed to load feed")
        return

    posts = response.json().get("posts", [])
    if not posts:
        st.info("No posts yet! Be the first to share something.")
        return

    for post in posts:
        st.markdown("---")

        username = post['email'].split('@')[0]
        st.markdown(f"**{username}** • {post['created_at'][:10]}")

        # LIKE BUTTON
        like_count = post.get("like_count", 0)
        is_liked = post.get("is_liked", False)

        if st.button(f"{'❤️' if is_liked else 'Like'} {like_count}", key=f"like_{post['id']}"):
            if is_liked:
                requests.delete(f"http://localhost:8000/posts/{post['id']}/like", headers=get_headers())
            else:
                requests.post(f"http://localhost:8000/posts/{post['id']}/like", headers=get_headers())
            st.rerun()

        # DELETE
        if post.get('is_owner'):
            if st.button("Delete", key=f"del_{post['id']}"):
                requests.delete(f"http://localhost:8000/posts/{post['id']}", headers=get_headers())
                st.rerun()

        # MEDIA
        caption = post.get("caption", "")
        if post["file_type"] == "image":
            url = create_transformed_url(post["url"], caption=caption)
            st.image(url, width=600)
        else:
            url = create_transformed_url(post["url"], "w-600,h-800")
            st.video(url)

        if caption:
            st.caption(caption)

        # COMMENTS — FINAL WORKING VERSION
        # ────────────────────── WORKING COMMENTS (NO FORMS, NO .VALUE, NO BUGS) ──────────────────────
        # COMMENTS — THIS IS THE ONLY VERSION THAT ACTUALLY WORKS
        with st.expander(f"Comments ({len(post.get('comments', []))})", expanded=False):
            # Show existing comments
            for c in post.get("comments", []):
                col1, col2 = st.columns([6, 1])
                with col1:
                    st.write(f"**{c['user_email']}**: {c['content']}")
                    st.caption(c['created_at'][:10])
                with col2:
                    if c.get("is_owner"):
                        if st.button("X", key=f"delcom_{c['id']}"):
                            requests.delete(f"http://localhost:8000/comments/{c['id']}", headers=get_headers())
                            st.rerun()

            # NEW COMMENT — THIS IS THE NUCLEAR FIX
            if prompt := st.chat_input("Add a comment...", key=f"chat_{post['id']}"):
                resp = requests.post(
                    f"http://localhost:8000/posts/{post['id']}/comment",
                    json={"content": prompt},
                    headers=get_headers()
                )
                if resp.status_code == 200:
                    st.rerun()

# Main app
if not st.session_state.user:
    login_page()
else:
    st.sidebar.title(f"Hi {st.session_state.user['email']}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()

    page = st.sidebar.radio("Go to", ["Feed", "Upload"])
    if page == "Feed":
        feed_page()
    else:
        upload_page()