import 'package:flutter/material.dart';

class TenantBrand {
  const TenantBrand({
    required this.appName,
    required this.bundleId,
    required this.tenantCode,
    required this.primaryColor,
    required this.apiAdapterBase,
    required this.supportedLocales,
    required this.customerServiceUrl,
    required this.termsUrl,
    required this.privacyUrl,
  });

  final String appName;
  final String bundleId;
  final String tenantCode;
  final Color primaryColor;
  final String apiAdapterBase;
  final List<String> supportedLocales;
  final String customerServiceUrl;
  final String termsUrl;
  final String privacyUrl;
}
