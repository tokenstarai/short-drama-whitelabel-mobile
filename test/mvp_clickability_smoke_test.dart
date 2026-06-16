import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/app/demo_adapter_transport.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/catalog/catalog_screen.dart';
import 'package:short_drama_whitelabel/features/home/home_screen.dart';
import 'package:short_drama_whitelabel/features/wallet/wallet_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';
import 'package:short_drama_whitelabel/theme/template_theme.dart';

void main() {
  final flavors = <String, FlavorConfig Function()>{
    'coolshow': FlavorConfig.coolshow,
    'hongguo': FlavorConfig.hongguo,
    'douyin': FlavorConfig.douyin,
    'hippo': FlavorConfig.hippo,
    'reelshort': FlavorConfig.reelshort,
  };

  for (final entry in flavors.entries) {
    testWidgets('${entry.key} MVP visible entries are clickable', (
      tester,
    ) async {
      final flavor = entry.value();
      final runtime = AppRuntime(
        flavor: flavor,
        localeCode: 'en-US',
        endUserRef: 'anon:${entry.key}-mvp-clickability',
        isDemoMode: true,
        client: TenantAdapterClient(
          baseUri: Uri.parse('https://demo.${entry.key}.local'),
          transport: DemoAdapterTransport(
            flavor: flavor,
            endUserRef: 'anon:${entry.key}-mvp-clickability',
          ),
        ),
      );
      addTearDown(runtime.dispose);

      await tester.pumpWidget(_Harness(runtime: runtime));
      await tester.pumpAndSettle();

      expect(find.text('Home'), findsWidgets);
      expect(find.text('Catalog'), findsWidgets);
      expect(find.text('Theater'), findsWidgets);
      expect(find.text('Mine'), findsWidgets);

      await tester.tap(find.text('Catalog').last);
      await tester.pumpAndSettle();
      expect(find.byType(CatalogScreen), findsOneWidget);
      await tester.tap(find.byType(TextButton).first);
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);

      await tester.tap(find.text('Mine').last);
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('Settings'), 360);
      await tester.tap(find.text('Settings'));
      await tester.pumpAndSettle();
      expect(find.text('Payment providers'), findsOneWidget);
      expect(tester.takeException(), isNull);

      Navigator.of(tester.element(find.text('Payment providers'))).pop();
      await tester.pumpAndSettle();
      await tester.tap(find.text('Home').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Mine').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Wallet Center'));
      await tester.pumpAndSettle();
      expect(find.byType(WalletScreen), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }
}

class _Harness extends StatelessWidget {
  const _Harness({required this.runtime});

  final AppRuntime runtime;

  @override
  Widget build(BuildContext context) {
    final tokens = templateTokensFor(
      runtime.effectiveCapabilities.styleTemplate,
      runtime.effectiveBrandPrimaryColor,
    );
    return AppRuntimeScope(
      runtime: runtime,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: tokens.primary,
            brightness: tokens.background.computeLuminance() < 0.25
                ? Brightness.dark
                : Brightness.light,
          ),
          useMaterial3: true,
          scaffoldBackgroundColor: tokens.background,
        ),
        home: HomeScreen(flavor: runtime.flavor),
      ),
    );
  }
}
