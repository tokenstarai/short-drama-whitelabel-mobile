import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/app/demo_adapter_transport.dart';
import 'package:short_drama_whitelabel/app/short_drama_app.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/account_delete/account_delete_screen.dart';
import 'package:short_drama_whitelabel/features/auth/auth_screen.dart';
import 'package:short_drama_whitelabel/features/player/player_screen.dart';
import 'package:short_drama_whitelabel/features/point_card_management/point_card_management_screen.dart';
import 'package:short_drama_whitelabel/features/wallet/wallet_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';
import 'package:short_drama_whitelabel/theme/template_theme.dart';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  group('CoolShow Android full function smoke', () {
    testWidgets('renders the Android shell and tenant navigation', (
      tester,
    ) async {
      final flavor = FlavorConfig.coolshow();

      await tester.pumpWidget(
        ShortDramaApp(
          flavor: flavor,
          loadRemoteConfig: false,
          endUserRef: 'anon:android-shell-smoke',
          deepLinks: const _NoopDeepLinks(),
        ),
      );

      await _pumpUntilFound(tester, find.text('CoolShow Short'));
      expect(find.text('CoolShow Short'), findsWidgets);
      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Catalog'), findsOneWidget);
      expect(find.text('Theater'), findsOneWidget);
      expect(find.text('Mine'), findsOneWidget);
      expect(find.text('Start Watching'), findsWidgets);

      await tester.tap(find.text('Catalog'));
      await tester.pumpAndSettle();
      expect(find.text('Latest'), findsOneWidget);
      expect(find.text('Ready first'), findsOneWidget);

      await tester.tap(find.text('Theater'));
      await tester.pumpAndSettle();
      expect(find.text('Start Watching'), findsWidgets);

      await tester.tap(find.text('Mine'));
      await tester.pumpAndSettle();
      expect(find.text('Wallet Center'), findsOneWidget);
      expect(find.text('Login / Register'), findsOneWidget);
      expect(find.text('Point Card Management'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Delete Account'),
        360,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      expect(find.text('Delete Account'), findsOneWidget);

      binding.reportData ??= <String, Object?>{};
      binding.reportData!['android_shell'] = 'passed';
    });

    testWidgets('runs email and social auth through demo Tenant Edge', (
      tester,
    ) async {
      final runtime = await _createDemoRuntime('anon:android-auth-smoke');
      addTearDown(runtime.dispose);

      await _pumpRuntimeScreen(
        tester,
        runtime,
        AuthScreen(
          flavor: runtime.flavor,
          callbackLinks: const _NoopOAuthCallbackLinks(),
        ),
      );

      await _tapText(tester, 'Sign in with Email');
      await _pumpUntilFound(tester, find.textContaining('Email challenge'));
      await _tapText(tester, 'Verify email');
      await _pumpUntilFound(tester, find.textContaining('Email verified'));
      expect(runtime.account?.membershipTier, 'registered');

      for (final provider in ['google', 'facebook', 'apple']) {
        await _tapText(tester, 'Continue with $provider');
        await _pumpUntilFound(
          tester,
          find.textContaining('$provider demo sign-in completed'),
        );
        expect(runtime.account?.authProviders, contains(provider));
      }

      binding.reportData ??= <String, Object?>{};
      binding.reportData!['android_auth'] = 'passed';
    });

    testWidgets('runs wallet, payment, top-up, and point-card flows', (
      tester,
    ) async {
      final runtime = await _createDemoRuntime('anon:android-wallet-smoke');
      addTearDown(runtime.dispose);
      final launchedCheckoutUrls = <Uri>[];

      await _pumpRuntimeScreen(
        tester,
        runtime,
        WalletScreen(
          flavor: runtime.flavor,
          launchPaymentUrl: (uri) async {
            launchedCheckoutUrls.add(uri);
            return true;
          },
        ),
      );

      await _pumpUntilFound(tester, find.text('Wallet Center'));
      expect(find.textContaining('480 coins'), findsWidgets);
      expect(find.text('Demo bank transfer'), findsOneWidget);
      expect(find.text('Demo local wallet'), findsOneWidget);
      expect(find.text('USDT/USDC demo address'), findsOneWidget);
      await _enterTransferProof(tester, 'android-smoke-proof-001');
      for (final provider in [
        'stripe',
        'paypal',
        'bank_transfer',
        'local_wallet',
        'crypto',
        'point_card',
      ]) {
        await _scrollToPayment(tester, provider);
        expect(
          find.byKey(ValueKey('payment-provider-$provider')),
          findsOneWidget,
        );
      }

      await _tapPaymentProvider(tester, 'stripe');
      await _pumpUntilFound(tester, find.textContaining('demo_paid'));
      await _tapPaymentProvider(tester, 'paypal');
      await _pumpUntilFound(tester, find.textContaining('demo_paid'));
      await _tapPaymentProvider(tester, 'bank_transfer');
      await _pumpUntilFound(tester, find.textContaining('pending_review'));
      await _tapPaymentProvider(tester, 'local_wallet');
      await _pumpUntilFound(tester, find.textContaining('pending_review'));
      await _tapPaymentProvider(tester, 'crypto');
      await _pumpUntilFound(tester, find.textContaining('pending_review'));
      expect(launchedCheckoutUrls, isEmpty);

      await _tapPaymentProvider(tester, 'point_card');
      await _pumpUntilFound(tester, find.text('Redeem Card'));
      await tester.enterText(
        find.widgetWithText(TextField, 'Card code'),
        'DEMO-VIP-ANDROID',
      );
      await tester.tap(find.widgetWithText(FilledButton, 'Redeem'));
      await _pumpUntilFound(tester, find.textContaining('credited 700 coins'));

      await _pumpRuntimeScreen(
        tester,
        runtime,
        PointCardManagementScreen(flavor: runtime.flavor),
      );
      await _pumpUntilFound(tester, find.byType(PointCardManagementScreen));
      expect(
        runtime.walletLedger?.entries.map((entry) => entry.title),
        contains('Point card redeemed'),
      );

      binding.reportData ??= <String, Object?>{};
      binding.reportData!['android_wallet_payments'] = 'passed';
    });

    testWidgets('runs playback, episode, favorite, share, and deletion flows', (
      tester,
    ) async {
      final runtime = await _createDemoRuntime('anon:android-player-smoke');
      addTearDown(runtime.dispose);
      final drama = runtime.catalog.first;
      final detail = await runtime.fetchDrama(drama.dramaId);

      await _pumpRuntimeScreen(
        tester,
        runtime,
        PlayerScreen(
          flavor: runtime.flavor,
          dramaId: drama.dramaId,
          episodeId: detail.episodes.first.episodeId,
          dramaTitle: drama.title,
          episodeTitle: detail.episodes.first.title,
          episodes: detail.episodes,
          enableNativeVideo: false,
        ),
      );

      await _tapText(tester, 'Unlock and Play');
      await _pumpUntilFound(tester, find.text('Authorized player'));
      expect(runtime.watchHistory, isNotEmpty);

      await tester.tap(find.byIcon(Icons.favorite_border));
      await tester.pumpAndSettle();
      expect(runtime.favorites.single.dramaId, drama.dramaId);

      await tester.tap(find.byIcon(Icons.share_outlined));
      await _pumpUntilFound(tester, find.text('Share Drama'));
      expect(
        find.textContaining(
          'coolshowshort://dramas/${drama.dramaId}/episodes/episode_1',
        ),
        findsOneWidget,
      );
      await tester.tapAt(const Offset(16, 16));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Next'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Episode 2'), findsWidgets);

      await _pumpRuntimeScreen(
        tester,
        runtime,
        AccountDeleteScreen(flavor: runtime.flavor),
      );
      await _pumpUntilFound(tester, find.text('Delete Account'));
      await tester.tap(find.text('Submit request'));
      await _pumpUntilFound(tester, find.textContaining('accepted for'));

      binding.reportData ??= <String, Object?>{};
      binding.reportData!['android_player_delete'] = 'passed';
    });
  });
}

Future<AppRuntime> _createDemoRuntime(String endUserRef) async {
  final flavor = FlavorConfig.coolshow();
  final runtime = AppRuntime(
    flavor: flavor,
    endUserRef: endUserRef,
    isDemoMode: true,
    client: TenantAdapterClient(
      baseUri: Uri.parse('https://demo.coolshow.local'),
      transport: DemoAdapterTransport(
        flavor: flavor,
        endUserRef: endUserRef,
      ),
    ),
  );
  await runtime.bootstrap();
  return runtime;
}

Future<void> _pumpRuntimeScreen(
  WidgetTester tester,
  AppRuntime runtime,
  Widget home,
) async {
  final tokens = templateTokensFor(
    runtime.effectiveCapabilities.styleTemplate,
    runtime.effectiveBrandPrimaryColor,
  );
  await tester.pumpWidget(
    AppRuntimeScope(
      runtime: runtime,
      child: MaterialApp(
        key: UniqueKey(),
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
        home: home,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

Future<void> _tapText(WidgetTester tester, String text) async {
  final finder = find.text(text);
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _enterTransferProof(WidgetTester tester, String value) async {
  final finder = find.widgetWithText(TextField, 'Transfer proof reference');
  await _resetPrimaryScroll(tester);
  await tester.scrollUntilVisible(
    finder,
    360,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
  await tester.enterText(finder, value);
  await tester.pumpAndSettle();
}

Future<void> _scrollToPayment(WidgetTester tester, String provider) async {
  await _resetPrimaryScroll(tester);
  await tester.scrollUntilVisible(
    find.byKey(ValueKey('payment-provider-$provider')),
    360,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
}

Future<void> _resetPrimaryScroll(WidgetTester tester) async {
  final scrollable = find.byType(Scrollable).first;
  for (var index = 0; index < 4; index += 1) {
    await tester.drag(scrollable, const Offset(0, 900));
    await tester.pump(const Duration(milliseconds: 60));
  }
  await tester.pumpAndSettle();
}

Future<void> _tapPaymentProvider(WidgetTester tester, String provider) async {
  final finder = find.byKey(ValueKey('payment-provider-$provider'));
  await _scrollToPayment(tester, provider);
  await tester.tap(finder);
  await tester.pumpAndSettle();
}

Future<void> _pumpUntilFound(
  WidgetTester tester,
  Finder finder, {
  Duration timeout = const Duration(seconds: 12),
}) async {
  final endAt = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(endAt)) {
    await tester.pump(const Duration(milliseconds: 100));
    if (finder.evaluate().isNotEmpty) {
      return;
    }
  }
  expect(finder, findsWidgets);
}

class _NoopDeepLinks implements AppDeepLinks {
  const _NoopDeepLinks();

  @override
  Future<Uri?> getInitialLink() async => null;

  @override
  Stream<Uri> get uriLinkStream => const Stream.empty();
}

class _NoopOAuthCallbackLinks implements OAuthCallbackLinks {
  const _NoopOAuthCallbackLinks();

  @override
  Future<Uri?> getInitialLink() async => null;

  @override
  Stream<Uri> get uriLinkStream => const Stream.empty();
}
