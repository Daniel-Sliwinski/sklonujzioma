# main.py
from performance_critique import main as run_performance_critique
from sklonuj_zioma import main as run_sklonuj_zioma

def main():
    print("Starting the application...")

    # Run sklonuj_zioma functionality
    print("Running sklonuj_zioma...")
    run_sklonuj_zioma()

    # Run performance_critique functionality
    print("Running performance_critique...")
    run_performance_critique()

    print("Application finished.")

if __name__ == "__main__":
    main()