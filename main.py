import uvicorn

def main():
    print("Starting VibeFm backend API...")
    # 0.0.0.0 so the Expo app on a phone / emulator can reach the dev server
    # over the local network (127.0.0.1 is only reachable from this machine).
    uvicorn.run("backend.app.app:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    main()
