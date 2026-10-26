# Все сценарии по методичке (задача 4.3)
$BASE = "http://localhost:8000"

Write-Host "=== 1. Основной путь ==="
curl.exe -s -X POST "$BASE/books" -H "Content-Type: application/json" `
  -d '{\"id\":\"b1\",\"title\":\"DDD\",\"total_copies\":1}'
curl.exe -s -X POST "$BASE/loans" -H "Content-Type: application/json" `
  -d '{\"loan_id\":\"l1\",\"book_id\":\"b1\",\"reader_id\":\"r1\",\"issued_on\":\"2026-10-01\",\"due_on\":\"2026-10-15\"}'
curl.exe -s -X POST "$BASE/loans/l1/issue"
curl.exe -s -X POST "$BASE/loans/l1/return" -H "Content-Type: application/json" `
  -d '{\"returned_on\":\"2026-10-10\",\"fine_rate\":0}'
curl.exe -s "$BASE/loans/l1"

Write-Host "`n=== 2. Альтернатива: бронь истекла ==="
curl.exe -s -X POST "$BASE/loans" -H "Content-Type: application/json" `
  -d '{\"loan_id\":\"l2\",\"book_id\":\"b1\",\"reader_id\":\"r2\",\"issued_on\":\"2026-10-01\",\"due_on\":\"2026-10-15\"}'
curl.exe -s -X POST "$BASE/internal/tick" -H "Content-Type: application/json" `
  -d '{\"now\":\"2026-10-05T10:00:00\"}'
curl.exe -s "$BASE/loans/l2"

Write-Host "`n=== 3. Просрочка и эскалация ==="
curl.exe -s -X POST "$BASE/loans" -H "Content-Type: application/json" `
  -d '{\"loan_id\":\"l3\",\"book_id\":\"b1\",\"reader_id\":\"r3\",\"issued_on\":\"2026-10-10\",\"due_on\":\"2026-10-20\"}'
curl.exe -s -X POST "$BASE/loans/l3/issue"
curl.exe -s -X POST "$BASE/internal/tick" -H "Content-Type: application/json" `
  -d '{\"now\":\"2026-10-25T10:00:00\"}'
curl.exe -s "$BASE/loans/l3"
curl.exe -s -X POST "$BASE/internal/tick" -H "Content-Type: application/json" `
  -d '{\"now\":\"2026-11-30T10:00:00\"}'
curl.exe -s "$BASE/loans/l3"

Write-Host "`n=== 4. Недопустимое событие (409) ==="
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$BASE/loans/l3/return" `
  -H "Content-Type: application/json" -d '{\"returned_on\":\"2026-10-11\",\"fine_rate\":0}'

Write-Host "=== 5. Некорректные данные (422) ==="
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$BASE/loans" `
  -H "Content-Type: application/json" `
  -d '{\"loan_id\":\"lx\",\"book_id\":\"b1\",\"reader_id\":\"r1\",\"issued_on\":\"2026-10-20\",\"due_on\":\"2026-10-10\"}'

Write-Host "=== 6. Несуществующая сущность (404) ==="
curl.exe -s -o NUL -w "%{http_code}`n" "$BASE/loans/unknown"

Write-Host "=== 7. Перевод часов назад (422) ==="
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "$BASE/internal/tick" `
  -H "Content-Type: application/json" -d '{\"now\":\"2020-01-01T00:00:00\"}'