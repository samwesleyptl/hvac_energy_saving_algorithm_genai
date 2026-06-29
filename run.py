"""
Smart AC Energy Saving Agent — Server Runner
Run this file to start the FastAPI server.
"""
import uvicorn

if __name__ == "__main__":
    print("=" * 56)
    print("  Smart AC Energy Saving Agent")
    print("  LangGraph + LangChain RAG Pipeline")
    print("=" * 56)
    print()
    print("  Starting server at: http://127.0.0.1:8000")
    print("  Dashboard:          http://127.0.0.1:8000/")
    print("  API docs:           http://127.0.0.1:8000/docs")
    print()
    print("  Press Ctrl+C to stop the server.")
    print()
    
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False
    )
