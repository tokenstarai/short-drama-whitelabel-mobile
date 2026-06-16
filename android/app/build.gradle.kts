plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.dramahub.shortdrama.whitelabel"
    compileSdk = flutter.compileSdkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "com.dramahub.shortdrama.whitelabel"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["appName"] = "Short Drama Whitelabel"
        manifestPlaceholders["deepLinkScheme"] = "shortdrama"
    }

    flavorDimensions += "template"
    productFlavors {
        create("coolshow") {
            dimension = "template"
            applicationId = "com.coolshow.short"
            manifestPlaceholders["appName"] = "CoolShow Short"
            manifestPlaceholders["deepLinkScheme"] = "coolshowshort"
        }
        create("hongguo") {
            dimension = "template"
            applicationId = "com.shortdrama.goldfruit"
            manifestPlaceholders["appName"] = "GoldFruit Drama"
            manifestPlaceholders["deepLinkScheme"] = "goldfruitdrama"
        }
        create("douyin") {
            dimension = "template"
            applicationId = "com.shortdrama.pulse"
            manifestPlaceholders["appName"] = "Pulse Drama"
            manifestPlaceholders["deepLinkScheme"] = "pulsedrama"
        }
        create("hippo") {
            dimension = "template"
            applicationId = "com.shortdrama.river"
            manifestPlaceholders["appName"] = "River Drama"
            manifestPlaceholders["deepLinkScheme"] = "riverdrama"
        }
        create("reelshort") {
            dimension = "template"
            applicationId = "com.shortdrama.cliff"
            manifestPlaceholders["appName"] = "Cliff Drama"
            manifestPlaceholders["deepLinkScheme"] = "cliffdrama"
        }
    }

    buildTypes {
        release {
            // Template builds use the debug key until each tenant supplies
            // store-owned signing material outside the repository.
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
