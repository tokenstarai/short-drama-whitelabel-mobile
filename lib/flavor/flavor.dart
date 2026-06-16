import 'package:flutter/material.dart';

import '../brand/tenant_brand.dart';
import '../core/config/app_capabilities.dart';
import '../core/config/feature_flags.dart';

enum AppFlavor {
  golden,
  purple,
  blue,
  coolshow,
  hongguo,
  douyin,
  hippo,
  reelshort,
}

class FlavorConfig {
  const FlavorConfig({
    required this.flavor,
    required this.brand,
    required this.features,
    required this.capabilities,
  });

  final AppFlavor flavor;
  final TenantBrand brand;
  final FeatureFlags features;
  final AppCapabilities capabilities;

  String get deepLinkScheme {
    return switch (flavor) {
      AppFlavor.coolshow => 'coolshowshort',
      AppFlavor.hongguo => 'goldfruitdrama',
      AppFlavor.douyin => 'pulsedrama',
      AppFlavor.hippo => 'riverdrama',
      AppFlavor.reelshort => 'cliffdrama',
      AppFlavor.golden => 'goldfruitdrama',
      AppFlavor.purple => 'riverdrama',
      AppFlavor.blue => 'pulsedrama',
    };
  }

  static FlavorConfig fromEnvironment() {
    const value =
        String.fromEnvironment('APP_FLAVOR', defaultValue: 'coolshow');
    return switch (value) {
      'purple' => purple(),
      'blue' => blue(),
      'coolshow' => coolshow(),
      'hongguo' => hongguo(),
      'douyin' => douyin(),
      'hippo' => hippo(),
      'reelshort' => reelshort(),
      _ => golden(),
    };
  }

  Map<String, Object> toPublicTemplateConfig() {
    return {
      'appName': brand.appName,
      'bundleId': brand.bundleId,
      'tenantCode': brand.tenantCode,
      'deepLinkScheme': deepLinkScheme,
      'apiAdapterBase': brand.apiAdapterBase,
      'supportedLocales': brand.supportedLocales,
      'legal': {
        'customerServiceUrl': brand.customerServiceUrl,
        'termsUrl': brand.termsUrl,
        'privacyUrl': brand.privacyUrl,
      },
      ...capabilities.toPublicJson(),
    };
  }

  static FlavorConfig golden() => hongguo();

  static FlavorConfig purple() => hippo();

  static FlavorConfig blue() => douyin();

  static FlavorConfig coolshow() {
    return const FlavorConfig(
      flavor: AppFlavor.coolshow,
      brand: TenantBrand(
        appName: 'CoolShow Short',
        bundleId: 'com.coolshow.short',
        tenantCode: 'coolshow',
        primaryColor: Color(0xFFFFB23F),
        apiAdapterBase:
            'https://short-drama-saas-tenant-edge-staging.tokenstarai.workers.dev',
        customerServiceUrl:
            'https://short-drama-saas-admin-staging.pages.dev/support',
        termsUrl: 'https://short-drama-saas-admin-staging.pages.dev/terms',
        privacyUrl: 'https://short-drama-saas-admin-staging.pages.dev/privacy',
        supportedLocales: [
          'en-US',
          'zh-CN',
          'id-ID',
          'th-TH',
          'vi-VN',
          'ms-MY',
          'fil-PH',
        ],
      ),
      features: FeatureFlags(
        enableCardRedeem: true,
        enableOfflineTopup: true,
        enableOnlinePayment: true,
        enableAdsUnlock: true,
        enableAccountDeletion: true,
      ),
      capabilities: AppCapabilities(
        styleTemplate: StyleTemplate.coolshow,
        storeComplianceMode: StoreComplianceMode.androidDirect,
        authProviders: {
          AuthProvider.email,
          AuthProvider.google,
          AuthProvider.facebook,
          AuthProvider.apple,
        },
        consumerPaymentProviders: {
          ConsumerPaymentProvider.stripe,
          ConsumerPaymentProvider.paypal,
          ConsumerPaymentProvider.bankTransfer,
          ConsumerPaymentProvider.localWallet,
          ConsumerPaymentProvider.crypto,
          ConsumerPaymentProvider.pointCard,
        },
      ),
    );
  }

  static FlavorConfig hongguo() {
    return const FlavorConfig(
      flavor: AppFlavor.hongguo,
      brand: TenantBrand(
        appName: 'GoldFruit Drama',
        bundleId: 'com.shortdrama.goldfruit',
        tenantCode: 'goldfruit',
        primaryColor: Color(0xFFE23A2E),
        apiAdapterBase:
            'https://short-drama-saas-tenant-edge-staging.tokenstarai.workers.dev',
        customerServiceUrl:
            'https://short-drama-saas-admin-staging.pages.dev/support',
        termsUrl: 'https://short-drama-saas-admin-staging.pages.dev/terms',
        privacyUrl: 'https://short-drama-saas-admin-staging.pages.dev/privacy',
        supportedLocales: [
          'en-US',
          'zh-CN',
          'th-TH',
          'id-ID',
          'vi-VN',
          'ms-MY',
          'fil-PH',
        ],
      ),
      features: FeatureFlags.defaults(),
      capabilities: AppCapabilities(
        styleTemplate: StyleTemplate.hongguoInspired,
        storeComplianceMode: StoreComplianceMode.appStore,
        authProviders: {
          AuthProvider.email,
          AuthProvider.google,
          AuthProvider.apple,
        },
        consumerPaymentProviders: {ConsumerPaymentProvider.iap},
      ),
    );
  }

  static FlavorConfig douyin() {
    return const FlavorConfig(
      flavor: AppFlavor.douyin,
      brand: TenantBrand(
        appName: 'Pulse Drama',
        bundleId: 'com.shortdrama.pulse',
        tenantCode: 'pulsedrama',
        primaryColor: Color(0xFF00D4FF),
        apiAdapterBase: 'https://pulse-tenant-edge.example.workers.dev',
        customerServiceUrl: 'https://tenant-edge.example.workers.dev/support',
        termsUrl: 'https://tenant-edge.example.workers.dev/terms',
        privacyUrl: 'https://tenant-edge.example.workers.dev/privacy',
        supportedLocales: ['zh-CN', 'en-US', 'th-TH'],
      ),
      features: FeatureFlags.defaults(),
      capabilities: AppCapabilities(
        styleTemplate: StyleTemplate.douyinInspired,
        storeComplianceMode: StoreComplianceMode.androidDirect,
        authProviders: {
          AuthProvider.email,
          AuthProvider.google,
          AuthProvider.facebook,
        },
        consumerPaymentProviders: {
          ConsumerPaymentProvider.stripe,
          ConsumerPaymentProvider.paypal,
          ConsumerPaymentProvider.bankTransfer,
          ConsumerPaymentProvider.localWallet,
          ConsumerPaymentProvider.crypto,
          ConsumerPaymentProvider.pointCard,
        },
      ),
    );
  }

  static FlavorConfig hippo() {
    return const FlavorConfig(
      flavor: AppFlavor.hippo,
      brand: TenantBrand(
        appName: 'River Drama',
        bundleId: 'com.shortdrama.river',
        tenantCode: 'riverdrama',
        primaryColor: Color(0xFF0EA5A4),
        apiAdapterBase: 'https://river-tenant-edge.example.workers.dev',
        customerServiceUrl: 'https://tenant-edge.example.workers.dev/support',
        termsUrl: 'https://tenant-edge.example.workers.dev/terms',
        privacyUrl: 'https://tenant-edge.example.workers.dev/privacy',
        supportedLocales: ['zh-CN', 'en-US', 'ms-MY'],
      ),
      features: FeatureFlags.defaults(),
      capabilities: AppCapabilities(
        styleTemplate: StyleTemplate.hippoInspired,
        storeComplianceMode: StoreComplianceMode.appStore,
        authProviders: {AuthProvider.email, AuthProvider.apple},
        consumerPaymentProviders: {ConsumerPaymentProvider.iap},
      ),
    );
  }

  static FlavorConfig reelshort() {
    return const FlavorConfig(
      flavor: AppFlavor.reelshort,
      brand: TenantBrand(
        appName: 'Cliff Drama',
        bundleId: 'com.shortdrama.cliff',
        tenantCode: 'cliffdrama',
        primaryColor: Color(0xFFFFB23F),
        apiAdapterBase: 'https://cliff-tenant-edge.example.workers.dev',
        customerServiceUrl: 'https://tenant-edge.example.workers.dev/support',
        termsUrl: 'https://tenant-edge.example.workers.dev/terms',
        privacyUrl: 'https://tenant-edge.example.workers.dev/privacy',
        supportedLocales: ['en-US', 'id-ID', 'fil-PH'],
      ),
      features: FeatureFlags.defaults(),
      capabilities: AppCapabilities(
        styleTemplate: StyleTemplate.reelshortInspired,
        storeComplianceMode: StoreComplianceMode.playStore,
        authProviders: {AuthProvider.email, AuthProvider.google},
        consumerPaymentProviders: {ConsumerPaymentProvider.playBilling},
      ),
    );
  }
}
