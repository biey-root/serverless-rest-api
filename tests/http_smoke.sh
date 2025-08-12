#!/bin/bash
API="$1"
echo "Health check:"
curl -s "$API/health"
echo "\nCreate todo:"
curl -s -X POST "$API/todos" -H 'content-type: application/json' -d '{"title":"Test"}'
echo "\nList todos:"
curl -s "$API/todos"
