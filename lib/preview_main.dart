import 'package:flutter/material.dart';

import 'app/preview_app.dart';
import 'flavor/flavor.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const screenId = String.fromEnvironment('PREVIEW_SCREEN', defaultValue: '');
  const localeCode = String.fromEnvironment(
    'PREVIEW_LOCALE',
    defaultValue: 'en-US',
  );
  runApp(
    PreviewApp(
      flavor: FlavorConfig.fromEnvironment(),
      screenId: screenId.isEmpty ? 'home' : screenId,
      localeCode: localeCode,
    ),
  );
}
