import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/auth/auth_screen.dart';
import 'package:short_drama_whitelabel/features/catalog/catalog_screen.dart';
import 'package:short_drama_whitelabel/features/drama_detail/drama_detail_screen.dart';
import 'package:short_drama_whitelabel/features/home/home_screen.dart';
import 'package:short_drama_whitelabel/features/player/player_screen.dart';
import 'package:short_drama_whitelabel/features/splash/splash_screen.dart';
import 'package:short_drama_whitelabel/features/unlock/unlock_sheet.dart';
import 'package:short_drama_whitelabel/features/wallet/wallet_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';
import 'package:short_drama_whitelabel/theme/template_theme.dart';

const prototypeWidths = <double>[360, 390, 430, 768];
const prototypeHeight = 844.0;

final prototypeFlavors = <String, FlavorConfig Function()>{
  'coolshow': FlavorConfig.coolshow,
  'hongguo': FlavorConfig.hongguo,
  'douyin': FlavorConfig.douyin,
  'hippo': FlavorConfig.hippo,
  'reelshort': FlavorConfig.reelshort,
};

final prototypeScreens = <PrototypeScreen>[
  PrototypeScreen(
    id: '01_splash',
    label: 'Splash',
    build: (flavor) => _PrototypeScaffold(
      title: 'Splash',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SplashHeader(flavor: flavor),
          const Spacer(),
          const Icon(Icons.play_circle_fill_rounded, size: 88),
          const SizedBox(height: 18),
          Text(
            flavor.brand.appName,
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 8),
          const Text(
            'Loading tenant configuration',
            textAlign: TextAlign.center,
          ),
          const Spacer(),
        ],
      ),
    ),
  ),
  PrototypeScreen(
    id: '02_auth',
    label: 'Login / Register',
    build: (flavor) => AuthScreen(
      flavor: flavor,
      callbackLinks: PrototypeOAuthCallbackLinks(),
    ),
  ),
  PrototypeScreen(
    id: '03_home',
    label: 'Home',
    build: (flavor) => HomeScreen(flavor: flavor),
  ),
  PrototypeScreen(
    id: '04_catalog',
    label: 'Catalog / Theater',
    build: (flavor) => Scaffold(
      body: SafeArea(child: CatalogScreen(flavor: flavor)),
    ),
  ),
  PrototypeScreen(
    id: '05_detail',
    label: 'Drama Detail',
    build: (flavor) => DramaDetailScreen(
      flavor: flavor,
      dramaId: 'drama_1',
    ),
  ),
  PrototypeScreen(
    id: '06_player',
    label: 'Vertical Player',
    build: (flavor) => PlayerScreen(
      flavor: flavor,
      dramaId: 'drama_1',
      episodeId: 'episode_1',
      dramaTitle: 'Contract Wife',
      episodeTitle: 'Episode 1',
    ),
  ),
  PrototypeScreen(
    id: '07_unlock',
    label: 'Unlock / Recharge',
    build: (flavor) => _UnlockPreview(flavor: flavor),
    afterPump: (tester) async {
      await tester.tap(find.text('Open unlock sheet'));
      await tester.pumpAndSettle();
    },
  ),
  PrototypeScreen(
    id: '08_mine_wallet_card',
    label: 'Mine / Wallet / Point Card',
    build: (flavor) => WalletScreen(flavor: flavor),
  ),
];

class PrototypeScreen {
  const PrototypeScreen({
    required this.id,
    required this.label,
    required this.build,
    this.afterPump,
  });

  final String id;
  final String label;
  final Widget Function(FlavorConfig flavor) build;
  final Future<void> Function(WidgetTester tester)? afterPump;
}

class PrototypeOAuthCallbackLinks implements OAuthCallbackLinks {
  @override
  Future<Uri?> getInitialLink() async => null;

  @override
  Stream<Uri> get uriLinkStream => const Stream.empty();
}

class PrototypeTransport implements AdapterTransport {
  @override
  Future<AdapterResponse> send(AdapterRequest request) async {
    return AdapterResponse(statusCode: 200, body: jsonEncode(_body(request)));
  }

  Map<String, Object?> _body(AdapterRequest request) {
    if (request.path == '/dramas/drama_1') {
      return {
        'requestId': 'prototype_detail',
        'status': 'ok',
        'drama': {
          'dramaId': 'drama_1',
          'title': 'Contract Wife',
          'posterUrl': '/assets/posters/midnight.png',
          'episodeCount': 36,
          'readyEpisodeCount': 8,
          'pointPrice': 2,
          'episodes': [
            for (var index = 0; index < 12; index += 1)
              {
                'episodeId': index == 0
                    ? 'episode_1'
                    : 'drama_1_ep_${(index + 1).toString().padLeft(3, '0')}',
                'episodeNumber': index + 1,
                'title': 'Episode ${index + 1}',
                'pointPrice': 2,
                'ready': index < 8,
                'locked': index > 0,
              },
          ],
        },
      };
    }
    if (request.path == '/play') {
      return {
        'requestId': 'prototype_play',
        'grantId': 'grant_prototype',
        'charge': {'points': 2, 'balanceAfter': 46},
        'playback': {
          'playerUrl': 'https://player.example/prototype',
          'manifestHost': 'stream.example',
          'tokenExpiresAt': '2026-06-14T00:00:00Z',
        },
      };
    }
    if (request.path == '/payment/options') {
      return {
        'requestId': 'prototype_payment_options',
        'providers': [
          'iap',
          'play_billing',
          'stripe',
          'paypal',
          'bank_transfer',
          'local_wallet',
          'crypto',
          'point_card',
        ],
        'externalPaymentsAllowed': true,
        'ledgerScope': 'consumer',
        'storeComplianceMode': 'android_direct',
      };
    }
    if (request.path == '/topups/payment-channels') {
      return {
        'requestId': 'prototype_payment_channels',
        'status': 'ok',
        'channels': [
          {
            'id': 'payment_prototype_bank',
            'country': 'ID',
            'method': 'Bank Transfer',
            'name': 'BCA Bank',
            'summary': 'account: 123***7800',
            'enabled': true,
            'qrFileName': 'bca-bank-qr.png',
            'qrImageUrl':
                'https://media.example.test/payment-qrs/bca-bank-qr.png',
          },
        ],
      };
    }
    if (request.path == '/wallet') {
      return {
        'requestId': 'prototype_wallet',
        'wallet': {
          'tenantId': 'tenant_prototype',
          'accountRefMasked': 'anon:p...type',
          'ledgerScope': 'consumer',
          'balanceCoins': 48,
          'membershipTier': 'guest',
          'currency': 'coins',
        },
      };
    }
    if (request.path == '/wallet/ledger') {
      return {
        'requestId': 'prototype_wallet_ledger',
        'ledgerScope': 'consumer',
        'accountRefMasked': 'anon:p...type',
        'entries': [
          {
            'ledgerId': 'prototype_ledger_1',
            'type': 'point_card',
            'title': 'Point card recharge',
            'pointsDelta': 48,
            'balanceAfter': 48,
            'createdAt': '2026-06-14T00:00:00Z',
            'status': 'posted',
          },
        ],
      };
    }
    if (request.path == '/me') {
      return {
        'requestId': 'prototype_me',
        'account': {
          'tenantId': 'tenant_prototype',
          'accountRefMasked': 'anon:p...type',
          'authProviders': ['email', 'google', 'apple'],
          'membershipTier': 'guest',
          'deletionEndpoint': '/me/delete-request',
        },
      };
    }
    return {'requestId': 'prototype_ok', 'status': 'ok'};
  }
}

Future<void> pumpPrototypeScreen(
  WidgetTester tester, {
  required FlavorConfig flavor,
  required PrototypeScreen screen,
  required double width,
}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, prototypeHeight);
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);

  final runtime = AppRuntime(
    flavor: flavor,
    localeCode: 'en-US',
    client: TenantAdapterClient(
      baseUri: Uri.parse('https://tenant-edge.example.test'),
      transport: PrototypeTransport(),
    ),
  );
  addTearDown(runtime.dispose);

  await tester.pumpWidget(_PrototypeApp(runtime: runtime, screen: screen));
  await tester.pumpAndSettle();
  await screen.afterPump?.call(tester);
}

class _PrototypeApp extends StatelessWidget {
  const _PrototypeApp({required this.runtime, required this.screen});

  final AppRuntime runtime;
  final PrototypeScreen screen;

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
        title: '${runtime.appName} ${screen.label}',
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
        home: screen.build(runtime.flavor),
      ),
    );
  }
}

class _PrototypeScaffold extends StatelessWidget {
  const _PrototypeScaffold({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: SafeArea(
        child: Padding(padding: const EdgeInsets.all(16), child: child),
      ),
    );
  }
}

class _UnlockPreview extends StatelessWidget {
  const _UnlockPreview({required this.flavor});

  final FlavorConfig flavor;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: FilledButton(
            onPressed: () => showUnlockSheet(context, flavor: flavor),
            child: const Text('Open unlock sheet'),
          ),
        ),
      ),
    );
  }
}
