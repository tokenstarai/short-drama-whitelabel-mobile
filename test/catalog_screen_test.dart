import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/app_models.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/catalog/catalog_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class CatalogNoopTransport implements AdapterTransport {
  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    return AdapterResponse(
      statusCode: 200,
      body: jsonEncode({'requestId': 'noop', 'status': 'ok'}),
    );
  }
}

AppRuntime catalogRuntime(
  List<CatalogDrama> catalog, {
  CatalogDisplayConfig catalogDisplay = const CatalogDisplayConfig.empty(),
}) {
  final flavor = FlavorConfig.hongguo();
  final runtime = AppRuntime(
    flavor: flavor,
    client: TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: CatalogNoopTransport(),
    ),
  );
  runtime.data = AppRuntimeData(
    config: AppConfig(
      requestId: 'config_catalog_test',
      tenantId: 'tenant_catalog_test',
      appKey: 'pk_catalog_test',
      appName: flavor.brand.appName,
      brandName: flavor.brand.appName,
      defaultLocale: 'en-US',
      supportedLocales: const ['en-US', 'zh-CN'],
      features: const {},
      capabilities: flavor.capabilities,
      legal: AppLegalUrls(
        customerServiceUrl: flavor.brand.customerServiceUrl,
        termsUrl: flavor.brand.termsUrl,
        privacyUrl: flavor.brand.privacyUrl,
      ),
      catalogDisplay: catalogDisplay,
    ),
    catalog: catalog,
    account: runtime.data.account,
    wallet: runtime.data.wallet,
    walletLedger: runtime.data.walletLedger,
    paymentOptions: runtime.data.paymentOptions,
    topupPaymentChannels: runtime.data.topupPaymentChannels,
  );
  return runtime;
}

Future<void> pumpCatalog(
  WidgetTester tester,
  List<CatalogDrama> catalog, {
  String initialQuery = '',
  CatalogDisplayConfig catalogDisplay = const CatalogDisplayConfig.empty(),
}) async {
  final runtime = catalogRuntime(catalog, catalogDisplay: catalogDisplay);
  await tester.pumpWidget(
    AppRuntimeScope(
      runtime: runtime,
      child: MaterialApp(
        home: Scaffold(
          body: SafeArea(
            child: CatalogScreen(
              flavor: runtime.flavor,
              catalog: catalog,
              initialQuery: initialQuery,
            ),
          ),
        ),
      ),
    ),
  );
}

const catalogFixtures = [
  CatalogDrama(
    dramaId: 'river',
    title: 'River Vow',
    summary: 'Cross-border romance in Jakarta.',
    posterUrl: '/posters/river.png',
    episodeCount: 24,
    readyEpisodeCount: 9,
    pointPrice: 1,
    language: 'id-ID',
    regions: ['ID'],
    tags: ['Romance', 'Trending'],
    categorySelections: {
      'genre': ['romance'],
      'market': ['ID'],
    },
  ),
  CatalogDrama(
    dramaId: 'palace',
    title: 'Palace Revenge',
    summary: 'Court intrigue with daily cliffhangers.',
    posterUrl: '/posters/palace.png',
    episodeCount: 40,
    readyEpisodeCount: 18,
    pointPrice: 5,
    language: 'th-TH',
    regions: ['TH'],
    tags: ['Revenge', 'Trending'],
    categorySelections: {
      'genre': ['revenge', 'mystery'],
      'market': ['TH'],
    },
  ),
  CatalogDrama(
    dramaId: 'city',
    title: 'City CEO',
    summary: 'Modern romance with a contract twist.',
    posterUrl: '/posters/city.png',
    episodeCount: 30,
    readyEpisodeCount: 12,
    pointPrice: 2,
    language: 'en-US',
    regions: ['TH', 'SG'],
    tags: ['Romance', 'Urban'],
    categorySelections: {
      'genre': ['romance', 'urban'],
      'market': ['TH', 'SG'],
    },
  ),
];

void main() {
  testWidgets('catalog search and chips filter by public metadata',
      (tester) async {
    await pumpCatalog(tester, catalogFixtures);

    expect(find.text('River Vow'), findsWidgets);
    expect(find.text('Palace Revenge'), findsWidgets);
    expect(find.text('City CEO'), findsWidgets);

    await tester.enterText(find.byType(TextField), 'river');
    await tester.pump();

    expect(find.text('River Vow'), findsWidgets);
    expect(find.text('Palace Revenge'), findsNothing);
    expect(find.text('City CEO'), findsNothing);
    expect(find.text('1 drama'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '');
    await tester.pump();
    await tester.tap(find.widgetWithText(FilterChip, 'Romance'));
    await tester.pump();

    expect(find.text('River Vow'), findsWidgets);
    expect(find.text('City CEO'), findsWidgets);
    expect(find.text('Palace Revenge'), findsNothing);

    await tester.tap(find.widgetWithText(FilterChip, 'TH'));
    await tester.pump();

    expect(find.text('City CEO'), findsWidgets);
    expect(find.text('River Vow'), findsNothing);
    expect(find.text('Palace Revenge'), findsNothing);
    expect(find.text('1 drama'), findsOneWidget);
  });

  testWidgets('catalog can sort visible dramas by lowest coin price first',
      (tester) async {
    await pumpCatalog(tester, catalogFixtures);

    await tester.tap(find.text('Lowest coins'));
    await tester.pump();

    final river = tester.getTopLeft(find.text('River Vow').last);
    final city = tester.getTopLeft(find.text('City CEO').last);
    final palace = tester.getTopLeft(find.text('Palace Revenge').last);

    expect(river.dy, lessThan(palace.dy));
    expect(river.dx, lessThan(city.dx));
  });

  testWidgets('catalog applies initial query from upstream search route',
      (tester) async {
    await pumpCatalog(tester, catalogFixtures, initialQuery: 'palace');

    expect(find.text('Palace Revenge'), findsWidgets);
    expect(find.text('River Vow'), findsNothing);
    expect(find.text('City CEO'), findsNothing);
    expect(find.text('1 drama'), findsOneWidget);
  });

  testWidgets('template tabs drive real catalog filtering', (tester) async {
    await pumpCatalog(tester, catalogFixtures);

    await tester.tap(find.widgetWithText(TextButton, 'Romance'));
    await tester.pump();

    expect(find.text('River Vow'), findsWidgets);
    expect(find.text('City CEO'), findsWidgets);
    expect(find.text('Palace Revenge'), findsNothing);
    expect(find.text('2 dramas'), findsOneWidget);
  });

  testWidgets('tenant catalog display config renames and hides categories',
      (tester) async {
    await pumpCatalog(
      tester,
      catalogFixtures,
      catalogDisplay: const CatalogDisplayConfig(
        optionLabels: {
          'romance': 'Sweet Love',
          'mystery': 'Mystery Hidden',
        },
        hiddenOptionIds: ['mystery'],
      ),
    );

    expect(find.widgetWithText(FilterChip, 'Sweet Love'), findsOneWidget);
    expect(find.widgetWithText(FilterChip, 'Mystery Hidden'), findsNothing);

    await tester.tap(find.widgetWithText(FilterChip, 'Sweet Love'));
    await tester.pump();

    expect(find.text('River Vow'), findsWidgets);
    expect(find.text('City CEO'), findsWidgets);
    expect(find.text('Palace Revenge'), findsNothing);
  });
}
