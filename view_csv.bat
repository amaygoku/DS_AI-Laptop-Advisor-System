@echo off
echo ========== OLD DATA: laptops_features.csv ==========
powershell -Command "Get-Content data\laptops_features.csv -TotalCount 3"

echo.
echo ========== NEW DATA: laptops_features3.csv ==========
powershell -Command "Get-Content data\laptops_features3.csv -TotalCount 3"
