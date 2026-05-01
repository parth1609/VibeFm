import uvicorn

def main():
    print("Starting VibeFm backend API...")
    uvicorn.run("backend.app.app:app", host="127.0.0.1", port=8000, reload=True)

if __name__ == "__main__":
    main()
