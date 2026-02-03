# NRW Android TV ProGuard Rules

# Keep data classes for Gson
-keepclassmembers class com.nrw.app.data.** { *; }

# Retrofit
-keepattributes Signature
-keepattributes Exceptions
-keepclasseswithmembers class * {
    @retrofit2.http.* <methods>;
}

# Gson
-keepattributes *Annotation*
-keep class com.google.gson.** { *; }

# Coil
-dontwarn coil.**
