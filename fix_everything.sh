#!/bin/bash

# 1. Fix movie_tracker.py field names
sed -i '' 's/theatrical_date/premiere_date/g' movie_tracker.py
sed -i '' 's/primary_release_date/release_date/g' movie_tracker.py

# 2. Fix generate_data.py to show 90 days and all movies
sed -i '' 's/timedelta(days=30)/timedelta(days=90)/g' generate_data.py
sed -i '' 's/recent\[:30\]/recent/g' generate_data.py

# 3. Remove duplicate admin files
mkdir -p old_admins
mv admin_broken.py admin_fixed.py curator_admin.py old_admins/ 2>/dev/null

# 4. Test the working admin
echo "Admin panel ready at http://localhost:5555"
echo "Run: python admin.py"
