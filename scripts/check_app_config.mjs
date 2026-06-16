#!/usr/bin/env node
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const mobileDir = join(scriptDir, "..");

const flavors = {
  coolshow: {
    appName: "CoolShow Short",
    bundleId: "com.coolshow.short",
    tenantCode: "coolshow",
    primaryColor: "#FFB23F",
    styleTemplate: "coolshow",
    styleEnum: "StyleTemplate.coolshow",
    compliance: "android_direct",
    complianceEnum: "StoreComplianceMode.androidDirect",
    apiAdapterBase: "https://short-drama-saas-tenant-edge-staging.tokenstarai.workers.dev",
    deepLinkScheme: "coolshowshort",
    dartDefine: "QVBQX0ZMQVZPUj1jb29sc2hvdw==",
    authProviders: ["email", "google", "facebook", "apple"],
    paymentProviders: ["stripe", "paypal", "bank_transfer", "local_wallet", "crypto", "point_card"],
  },
  hongguo: {
    appName: "GoldFruit Drama",
    bundleId: "com.shortdrama.goldfruit",
    tenantCode: "goldfruit",
    primaryColor: "#E23A2E",
    styleTemplate: "hongguo_inspired",
    styleEnum: "StyleTemplate.hongguoInspired",
    compliance: "app_store",
    complianceEnum: "StoreComplianceMode.appStore",
    apiAdapterBase: "https://short-drama-saas-tenant-edge-staging.tokenstarai.workers.dev",
    deepLinkScheme: "goldfruitdrama",
    dartDefine: "QVBQX0ZMQVZPUj1ob25nZ3Vv",
    authProviders: ["email", "google", "apple"],
    paymentProviders: ["iap"],
  },
  douyin: {
    appName: "Pulse Drama",
    bundleId: "com.shortdrama.pulse",
    tenantCode: "pulsedrama",
    primaryColor: "#00D4FF",
    styleTemplate: "douyin_inspired",
    styleEnum: "StyleTemplate.douyinInspired",
    compliance: "android_direct",
    complianceEnum: "StoreComplianceMode.androidDirect",
    apiAdapterBase: "https://pulse-tenant-edge.example.workers.dev",
    deepLinkScheme: "pulsedrama",
    dartDefine: "QVBQX0ZMQVZPUj1kb3V5aW4=",
    authProviders: ["email", "google", "facebook"],
    paymentProviders: ["stripe", "paypal", "bank_transfer", "local_wallet", "crypto", "point_card"],
  },
  hippo: {
    appName: "River Drama",
    bundleId: "com.shortdrama.river",
    tenantCode: "riverdrama",
    primaryColor: "#0EA5A4",
    styleTemplate: "hippo_inspired",
    styleEnum: "StyleTemplate.hippoInspired",
    compliance: "app_store",
    complianceEnum: "StoreComplianceMode.appStore",
    apiAdapterBase: "https://river-tenant-edge.example.workers.dev",
    deepLinkScheme: "riverdrama",
    dartDefine: "QVBQX0ZMQVZPUj1oaXBwbw==",
    authProviders: ["email", "apple"],
    paymentProviders: ["iap"],
  },
  reelshort: {
    appName: "Cliff Drama",
    bundleId: "com.shortdrama.cliff",
    tenantCode: "cliffdrama",
    primaryColor: "#FFB23F",
    styleTemplate: "reelshort_inspired",
    styleEnum: "StyleTemplate.reelshortInspired",
    compliance: "play_store",
    complianceEnum: "StoreComplianceMode.playStore",
    apiAdapterBase: "https://cliff-tenant-edge.example.workers.dev",
    deepLinkScheme: "cliffdrama",
    dartDefine: "QVBQX0ZMQVZPUj1yZWVsc2hvcnQ=",
    authProviders: ["email", "google"],
    paymentProviders: ["play_billing"],
  },
};

const compliancePaymentMatrix = {
  app_store: new Set(["iap"]),
  play_store: new Set(["play_billing"]),
  regional_user_choice: new Set(["play_billing", "stripe", "paypal", "bank_transfer", "local_wallet", "point_card"]),
  android_direct: new Set(["stripe", "paypal", "bank_transfer", "local_wallet", "crypto", "point_card"]),
};

function fail(message) {
  console.error(`app config check failed: ${message}`);
  process.exit(1);
}

function readText(path) {
  if (!existsSync(path)) {
    fail(`missing ${relative(mobileDir, path)}`);
  }
  return readFileSync(path, "utf8");
}

function readJson(path) {
  try {
    return JSON.parse(readText(path));
  } catch (error) {
    fail(`invalid JSON in ${relative(mobileDir, path)}: ${error.message}`);
  }
}

function requireIncludes(text, pattern, file) {
  if (!text.includes(pattern)) {
    fail(`missing '${pattern}' in ${relative(mobileDir, file)}`);
  }
}

function requireEqual(actual, expected, label) {
  if (actual !== expected) {
    fail(`${label} is '${actual}', expected '${expected}'`);
  }
}

function requireArrayEqual(actual, expected, label) {
  const actualSerialized = JSON.stringify(actual);
  const expectedSerialized = JSON.stringify(expected);
  if (actualSerialized !== expectedSerialized) {
    fail(`${label} is ${actualSerialized}, expected ${expectedSerialized}`);
  }
}

function localeLanguage(locale) {
  return String(locale).split(/[-_]/)[0].toLowerCase();
}

const availableLocaleLanguages = new Set(
  readdirSync(join(mobileDir, "lib/l10n"))
    .map((file) => /^app_([a-z_]+)\.arb$/.exec(file)?.[1])
    .filter(Boolean)
    .map((locale) => locale.split("_")[0]),
);

const flavorSource = readText(join(mobileDir, "lib/flavor/flavor.dart"));
const androidBuild = readText(join(mobileDir, "android/app/build.gradle.kts"));
const iosProject = readText(join(mobileDir, "ios/Runner.xcodeproj/project.pbxproj"));
const iosEntitlementsPath = join(mobileDir, "ios/Runner/Runner.entitlements");
const iosEntitlements = readText(iosEntitlementsPath);

for (const [flavor, expected] of Object.entries(flavors)) {
  const configDir = join(mobileDir, "assets/config", flavor);
  const brand = readJson(join(configDir, "tenant.brand.json"));
  const template = readJson(join(configDir, "tenant.template.json"));
  const features = readJson(join(configDir, "tenant.features.json"));

  requireEqual(brand.appName, expected.appName, `${flavor} brand appName`);
  requireEqual(brand.bundleId, expected.bundleId, `${flavor} brand bundleId`);
  requireEqual(brand.tenantCode, expected.tenantCode, `${flavor} brand tenantCode`);
  requireEqual(brand.primaryColor, expected.primaryColor, `${flavor} brand primaryColor`);
  requireEqual(brand.apiAdapterBase, expected.apiAdapterBase, `${flavor} brand apiAdapterBase`);
  requireEqual(template.styleTemplate, expected.styleTemplate, `${flavor} template styleTemplate`);
  requireEqual(template.storeComplianceMode, expected.compliance, `${flavor} template storeComplianceMode`);
  requireEqual(template.consumerLedgerScope, "consumer", `${flavor} template consumerLedgerScope`);
  requireArrayEqual(template.authProviders, expected.authProviders, `${flavor} template authProviders`);
  requireArrayEqual(template.consumerPaymentProviders, expected.paymentProviders, `${flavor} template consumerPaymentProviders`);

  for (const [key, value] of Object.entries(features)) {
    if (typeof value !== "boolean") {
      fail(`${flavor} feature ${key} must be boolean`);
    }
  }

  if (!Array.isArray(brand.supportedLocales) || brand.supportedLocales.length === 0) {
    fail(`${flavor} supportedLocales must be a non-empty array`);
  }
  for (const locale of brand.supportedLocales) {
    const language = localeLanguage(locale);
    if (!availableLocaleLanguages.has(language)) {
      fail(`${flavor} supported locale '${locale}' has no app_${language}.arb file`);
    }
  }

  if (!String(brand.apiAdapterBase).startsWith("https://")) {
    fail(`${flavor} apiAdapterBase must be https`);
  }
  for (const link of ["customerServiceUrl", "termsUrl", "privacyUrl"]) {
    if (!String(brand[link]).startsWith("https://")) {
      fail(`${flavor} ${link} must be https`);
    }
  }

  const allowedPayments = compliancePaymentMatrix[template.storeComplianceMode];
  for (const provider of template.consumerPaymentProviders) {
    if (!allowedPayments?.has(provider)) {
      fail(`${flavor} provider '${provider}' is not allowed for ${template.storeComplianceMode}`);
    }
  }
  if (
    template.storeComplianceMode === "app_store" &&
    (template.authProviders.includes("google") || template.authProviders.includes("facebook")) &&
    !template.authProviders.includes("apple")
  ) {
    fail(`${flavor} app_store config enables Google/Facebook without Apple auth`);
  }

  requireIncludes(flavorSource, `appName: '${expected.appName}'`, "lib/flavor/flavor.dart");
  requireIncludes(flavorSource, `bundleId: '${expected.bundleId}'`, "lib/flavor/flavor.dart");
  requireIncludes(flavorSource, `tenantCode: '${expected.tenantCode}'`, "lib/flavor/flavor.dart");
  requireIncludes(flavorSource, expected.apiAdapterBase, "lib/flavor/flavor.dart");
  requireIncludes(flavorSource, expected.styleEnum, "lib/flavor/flavor.dart");
  requireIncludes(flavorSource, expected.complianceEnum, "lib/flavor/flavor.dart");

  requireIncludes(androidBuild, `create("${flavor}")`, "android/app/build.gradle.kts");
  requireIncludes(androidBuild, `applicationId = "${expected.bundleId}"`, "android/app/build.gradle.kts");
  requireIncludes(androidBuild, `manifestPlaceholders["appName"] = "${expected.appName}"`, "android/app/build.gradle.kts");
  requireIncludes(androidBuild, `manifestPlaceholders["deepLinkScheme"] = "${expected.deepLinkScheme}"`, "android/app/build.gradle.kts");

  const iosConfigPath = join(mobileDir, `ios/Flutter/${flavor[0].toUpperCase()}${flavor.slice(1)}.xcconfig`);
  const iosConfig = readText(iosConfigPath);
  requireIncludes(iosConfig, `APP_DISPLAY_NAME=${expected.appName}`, iosConfigPath);
  requireIncludes(iosConfig, `APP_BUNDLE_IDENTIFIER=${expected.bundleId}`, iosConfigPath);
  requireIncludes(iosConfig, `APP_DEEP_LINK_SCHEME=${expected.deepLinkScheme}`, iosConfigPath);
  requireIncludes(iosConfig, `ASSETCATALOG_COMPILER_APPICON_NAME=AppIcon-${flavor}`, iosConfigPath);
  requireIncludes(iosConfig, `DART_DEFINES=$(inherited),${expected.dartDefine}`, iosConfigPath);

  const schemePath = join(mobileDir, `ios/Runner.xcodeproj/xcshareddata/xcschemes/${flavor}.xcscheme`);
  const scheme = readText(schemePath);
  requireIncludes(scheme, `Flutter/${flavor[0].toUpperCase()}${flavor.slice(1)}.xcconfig`, schemePath);
  requireIncludes(scheme, `value = "${flavor}"`, schemePath);
}

requireIncludes(iosProject, 'PRODUCT_BUNDLE_IDENTIFIER = "$(APP_BUNDLE_IDENTIFIER)"', "ios/Runner.xcodeproj/project.pbxproj");
requireIncludes(iosProject, "Runner.entitlements", "ios/Runner.xcodeproj/project.pbxproj");
requireIncludes(iosProject, "CODE_SIGN_ENTITLEMENTS = Runner/Runner.entitlements", "ios/Runner.xcodeproj/project.pbxproj");
requireIncludes(iosEntitlements, "com.apple.developer.applesignin", iosEntitlementsPath);
requireIncludes(iosEntitlements, "<string>Default</string>", iosEntitlementsPath);

const releaseManifestPath = join(mobileDir, "build/release-manifests/mobile-artifacts.json");
if (existsSync(releaseManifestPath)) {
  const manifest = readJson(releaseManifestPath);
  if (!Array.isArray(manifest.artifacts)) {
    fail("release manifest artifacts must be an array");
  }
  const serialized = JSON.stringify(manifest).toLowerCase();
  for (const marker of ["tenant_app_secret", "cloudflare_api_token", "client_secret", "stripe_secret", "paypal_secret", "private_key", "sk_"]) {
    if (serialized.includes(marker)) {
      fail(`release manifest contains forbidden marker '${marker}'`);
    }
  }
  for (const artifact of manifest.artifacts) {
    const expected = flavors[artifact.flavor];
    if (!expected) {
      fail(`release manifest contains unknown flavor '${artifact.flavor}'`);
    }
    requireEqual(artifact.styleTemplate, expected.styleTemplate, `${artifact.flavor} release manifest styleTemplate`);
    requireEqual(artifact.applicationId, expected.bundleId, `${artifact.flavor} release manifest applicationId`);
    requireEqual(artifact.deepLinkScheme, expected.deepLinkScheme, `${artifact.flavor} release manifest deepLinkScheme`);
    if (!/^[a-f0-9]{64}$/.test(String(artifact.sha256))) {
      fail(`${artifact.flavor} release manifest sha256 is invalid`);
    }
    if (!Number.isSafeInteger(artifact.sizeBytes) || artifact.sizeBytes <= 0) {
      fail(`${artifact.flavor} release manifest sizeBytes must be positive`);
    }
  }
}

console.log("Flutter app config contract is valid.");
