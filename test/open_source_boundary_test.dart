import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('mobile PRD set is packaged with the template', () {
    const requiredDocs = [
      'docs/prd/README.md',
      'docs/prd/00-current-state-audit.md',
      'docs/prd/01-mvp-function-units.md',
      'docs/prd/02-tenant-config-parity.md',
      'docs/prd/03-api-integration.md',
      'docs/prd/04-ios-android-ui-parity.md',
      'docs/prd/05-open-source-mobile-template.md',
      'docs/prd/06-high-fidelity-style-system.md',
    ];

    for (final path in requiredDocs) {
      expect(File(path).existsSync(), isTrue, reason: '$path is missing');
    }
  });

  test('mobile lib stays independent from backend and admin workspaces', () {
    final dartFiles = Directory('lib')
        .listSync(recursive: true)
        .whereType<File>()
        .where((file) => file.path.endsWith('.dart'));

    const deniedMarkers = [
      'apps/admin-h5',
      'apps/tenant-portal',
      'workers/',
      'packages/db',
      'packages/contracts',
      'TENANT_APP_SECRET',
      'CLOUDFLARE_API_TOKEN',
      'STRIPE_SECRET',
      'PAYPAL_SECRET',
      'WEBHOOK_SECRET',
      'service-account',
    ];

    for (final file in dartFiles) {
      final contents = file.readAsStringSync();
      for (final marker in deniedMarkers) {
        expect(
          contents,
          isNot(contains(marker)),
          reason: '${file.path} contains denied marker $marker',
        );
      }
    }
  });

  test('mobile pubspec has no local backend path dependencies', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();

    expect(pubspec, isNot(contains('../apps/')));
    expect(pubspec, isNot(contains('../workers/')));
    expect(pubspec, isNot(contains('../packages/')));
  });
}
