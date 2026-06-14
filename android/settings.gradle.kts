pluginManagement {
    val flutterSdkPath =
        run {
            val properties = java.util.Properties()
            val localProperties = file("local.properties")
            if (localProperties.exists()) {
                localProperties.inputStream().use { properties.load(it) }
            }
            val fallbackSdkPaths = listOf(
                System.getenv("FLUTTER_ROOT"),
                System.getenv("FLUTTER_HOME"),
                "/tmp/flutter".takeIf { file(it).exists() },
                "${System.getProperty("user.home")}/.local/flutter".takeIf { file(it).exists() },
            )
            val flutterSdkPath = properties.getProperty("flutter.sdk")
                ?: fallbackSdkPaths.firstOrNull { !it.isNullOrBlank() }
            require(flutterSdkPath != null) {
                "flutter.sdk not set. Add android/local.properties or set FLUTTER_ROOT."
            }
            flutterSdkPath
        }

    includeBuild("$flutterSdkPath/packages/flutter_tools/gradle")

    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

plugins {
    id("dev.flutter.flutter-plugin-loader") version "1.0.0"
    id("com.android.application") version "9.0.1" apply false
    id("org.jetbrains.kotlin.android") version "2.3.20" apply false
}

include(":app")
